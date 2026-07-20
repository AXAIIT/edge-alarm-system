#include <chrono>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

#ifdef _WIN32
#include <process.h>
#define getpid _getpid
#else
#include <unistd.h>
#endif

#include "rkllm.h"

using Clock = std::chrono::steady_clock;

struct Request {
    std::string request_id;
    std::string prompt;
    int max_output_tokens = 128;
    bool shutdown = false;
};

static LLMHandle g_llm_handle = nullptr;
static std::string g_output;
static Clock::time_point g_run_start;
static Clock::time_point g_first_token_time;
static Clock::time_point g_finish_time;
static bool g_seen_first_token = false;
static bool g_seen_finish = false;
static int g_request_count = 0;
static int g_model_load_count = 0;

static double ms_between(Clock::time_point start, Clock::time_point end) {
    return std::chrono::duration_cast<std::chrono::duration<double, std::milli>>(end - start).count();
}

static std::string json_escape(const std::string& value) {
    std::ostringstream out;
    out << '"';
    for (unsigned char ch : value) {
        switch (ch) {
            case '\\': out << "\\\\"; break;
            case '"': out << "\\\""; break;
            case '\b': out << "\\b"; break;
            case '\f': out << "\\f"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (ch < 0x20) {
                    out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(ch);
                } else {
                    out << ch;
                }
        }
    }
    out << '"';
    return out.str();
}

static int approx_tokens(const std::string& text) {
    int ascii_words = 0;
    bool in_word = false;
    int non_ascii_bytes = 0;
    int punct = 0;
    for (unsigned char ch : text) {
        if ((ch >= '0' && ch <= '9') || (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') || ch == '_') {
            if (!in_word) {
                ascii_words++;
                in_word = true;
            }
        } else {
            in_word = false;
            if (ch >= 0x80) {
                non_ascii_bytes++;
            } else if (ch > 0x20) {
                punct++;
            }
        }
    }
    int non_ascii_chars = (non_ascii_bytes + 2) / 3;
    int tokens = ascii_words + non_ascii_chars + punct;
    return tokens > 0 ? tokens : 0;
}

static void cleanup_and_exit(int code) {
    if (g_llm_handle != nullptr) {
        LLMHandle handle = g_llm_handle;
        g_llm_handle = nullptr;
        rkllm_destroy(handle);
    }
    std::exit(code);
}

static int callback(RKLLMResult* result, void* userdata, LLMCallState state) {
    (void)userdata;
    if (state == RKLLM_RUN_FINISH) {
        g_finish_time = Clock::now();
        g_seen_finish = true;
        return 0;
    }
    if (state == RKLLM_RUN_ERROR) {
        g_finish_time = Clock::now();
        g_seen_finish = true;
        return 0;
    }
    if (state == RKLLM_RUN_NORMAL && result != nullptr && result->text != nullptr) {
        if (!g_seen_first_token && std::strlen(result->text) > 0) {
            g_first_token_time = Clock::now();
            g_seen_first_token = true;
        }
        g_output += result->text;
    }
    return 0;
}

static bool decode_hex4(const std::string& hex, char32_t* value) {
    if (hex.size() != 4) {
        return false;
    }
    char32_t acc = 0;
    for (char ch : hex) {
        acc <<= 4;
        if (ch >= '0' && ch <= '9') {
            acc |= static_cast<char32_t>(ch - '0');
        } else if (ch >= 'a' && ch <= 'f') {
            acc |= static_cast<char32_t>(10 + ch - 'a');
        } else if (ch >= 'A' && ch <= 'F') {
            acc |= static_cast<char32_t>(10 + ch - 'A');
        } else {
            return false;
        }
    }
    *value = acc;
    return true;
}

static void append_utf8(char32_t cp, std::string* out) {
    if (cp <= 0x7F) {
        out->push_back(static_cast<char>(cp));
    } else if (cp <= 0x7FF) {
        out->push_back(static_cast<char>(0xC0 | (cp >> 6)));
        out->push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else if (cp <= 0xFFFF) {
        out->push_back(static_cast<char>(0xE0 | (cp >> 12)));
        out->push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
        out->push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else {
        out->push_back(static_cast<char>(0xF0 | (cp >> 18)));
        out->push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
        out->push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
        out->push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    }
}

static bool extract_json_string(const std::string& line, const std::string& key, std::string* out, std::string* error) {
    const std::string needle = "\"" + key + "\"";
    std::size_t key_pos = line.find(needle);
    if (key_pos == std::string::npos) {
        *error = "missing_key_" + key;
        return false;
    }
    std::size_t colon = line.find(':', key_pos + needle.size());
    if (colon == std::string::npos) {
        *error = "missing_colon_" + key;
        return false;
    }
    std::size_t i = line.find_first_not_of(" \t\r\n", colon + 1);
    if (i == std::string::npos || line[i] != '"') {
        *error = "missing_quote_" + key;
        return false;
    }
    ++i;
    std::string value;
    while (i < line.size()) {
        char ch = line[i++];
        if (ch == '"') {
            *out = value;
            return true;
        }
        if (ch != '\\') {
            value.push_back(ch);
            continue;
        }
        if (i >= line.size()) {
            *error = "bad_escape_" + key;
            return false;
        }
        char esc = line[i++];
        switch (esc) {
            case '"': value.push_back('"'); break;
            case '\\': value.push_back('\\'); break;
            case '/': value.push_back('/'); break;
            case 'b': value.push_back('\b'); break;
            case 'f': value.push_back('\f'); break;
            case 'n': value.push_back('\n'); break;
            case 'r': value.push_back('\r'); break;
            case 't': value.push_back('\t'); break;
            case 'u': {
                if (i + 4 > line.size()) {
                    *error = "bad_unicode_" + key;
                    return false;
                }
                char32_t cp = 0;
                if (!decode_hex4(line.substr(i, 4), &cp)) {
                    *error = "bad_unicode_" + key;
                    return false;
                }
                append_utf8(cp, &value);
                i += 4;
                break;
            }
            default:
                *error = "unsupported_escape_" + key;
                return false;
        }
    }
    *error = "unterminated_string_" + key;
    return false;
}

static bool extract_json_int(const std::string& line, const std::string& key, int* out, std::string* error) {
    const std::string needle = "\"" + key + "\"";
    std::size_t key_pos = line.find(needle);
    if (key_pos == std::string::npos) {
        *error = "missing_key_" + key;
        return false;
    }
    std::size_t colon = line.find(':', key_pos + needle.size());
    if (colon == std::string::npos) {
        *error = "missing_colon_" + key;
        return false;
    }
    std::size_t i = line.find_first_not_of(" \t\r\n", colon + 1);
    if (i == std::string::npos) {
        *error = "missing_value_" + key;
        return false;
    }
    std::size_t end = i;
    if (line[end] == '-') {
        ++end;
    }
    while (end < line.size() && line[end] >= '0' && line[end] <= '9') {
        ++end;
    }
    if (end == i) {
        *error = "bad_int_" + key;
        return false;
    }
    *out = std::atoi(line.substr(i, end - i).c_str());
    return true;
}

static bool parse_request(const std::string& line, Request* request, std::string* error) {
    if (line.find("\"command\"") != std::string::npos && line.find("\"shutdown\"") != std::string::npos) {
        request->shutdown = true;
        return true;
    }
    if (!extract_json_string(line, "request_id", &request->request_id, error)) {
        return false;
    }
    if (!extract_json_string(line, "prompt", &request->prompt, error)) {
        return false;
    }
    if (!extract_json_int(line, "max_output_tokens", &request->max_output_tokens, error)) {
        return false;
    }
    if (request->max_output_tokens <= 0) {
        *error = "max_output_tokens_must_be_positive";
        return false;
    }
    return true;
}

static void emit_ready(const std::string& status, const std::string& error, int max_context_len) {
    std::cout
        << "{"
        << "\"type\":\"ready\","
        << "\"status\":" << json_escape(status) << ","
        << "\"pid\":" << getpid() << ","
        << "\"model_load_count\":" << g_model_load_count << ","
        << "\"max_context_len\":" << max_context_len << ","
        << "\"error\":" << json_escape(error)
        << "}\n"
        << std::flush;
}

static void emit_response(
    const Request& request,
    int ret,
    double total_ms,
    const std::string& error
) {
    int prompt_tokens = approx_tokens(request.prompt);
    int output_tokens = approx_tokens(g_output);
    double first_token_ms = g_seen_first_token ? ms_between(g_run_start, g_first_token_time) : 0.0;
    double generate_ms = ms_between(g_run_start, g_seen_finish ? g_finish_time : Clock::now());
    double decode_tps = 0.0;
    if (output_tokens > 1 && generate_ms > first_token_ms) {
        decode_tps = (output_tokens - 1) / ((generate_ms - first_token_ms) / 1000.0);
    }
    std::cout
        << "{"
        << "\"type\":\"response\","
        << "\"request_id\":" << json_escape(request.request_id) << ","
        << "\"status\":" << json_escape(ret == 0 ? "ok" : "error") << ","
        << "\"request_index\":" << g_request_count << ","
        << "\"model_load_count\":" << g_model_load_count << ","
        << "\"pid\":" << getpid() << ","
        << "\"first_token_ms\":" << first_token_ms << ","
        << "\"prefill_ms\":" << first_token_ms << ","
        << "\"generate_time_ms\":" << generate_ms << ","
        << "\"total_time_ms\":" << total_ms << ","
        << "\"decode_tokens_per_s\":" << decode_tps << ","
        << "\"prompt_tokens\":" << prompt_tokens << ","
        << "\"output_tokens\":" << output_tokens << ","
        << "\"output_text\":" << json_escape(g_output) << ","
        << "\"exit_code\":" << ret << ","
        << "\"error\":" << json_escape(error)
        << "}\n"
        << std::flush;
}

static int run_request(const Request& request) {
    g_output.clear();
    g_seen_first_token = false;
    g_seen_finish = false;
    g_run_start = Clock::now();
    g_first_token_time = g_run_start;
    g_finish_time = g_run_start;

    RKLLMInput input;
    std::memset(&input, 0, sizeof(input));
    input.input_type = RKLLM_INPUT_PROMPT;
    input.role = const_cast<char*>("user");
    input.prompt_input = const_cast<char*>(request.prompt.c_str());

    RKLLMInferParam infer;
    std::memset(&infer, 0, sizeof(infer));
    infer.mode = RKLLM_INFER_GENERATE;
    infer.keep_history = 0;
    infer.max_new_tokens = request.max_output_tokens;

    return rkllm_run(g_llm_handle, &input, &infer, nullptr);
}

static void usage(const char* argv0) {
    std::cerr << "Usage: " << argv0
              << " --model <model.rkllm> --max-context-len <n>\n";
}

int main(int argc, char** argv) {
    std::signal(SIGINT, [](int) { cleanup_and_exit(130); });
    std::signal(SIGTERM, [](int) { cleanup_and_exit(143); });

    std::string model;
    int max_context_len = 2048;

    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if (arg == "--model" && i + 1 < argc) {
            model = argv[++i];
        } else if (arg == "--max-context-len" && i + 1 < argc) {
            max_context_len = std::atoi(argv[++i]);
        } else {
            usage(argv[0]);
            return 2;
        }
    }

    if (model.empty()) {
        usage(argv[0]);
        return 2;
    }

    RKLLMParam param = rkllm_createDefaultParam();
    param.model_path = const_cast<char*>(model.c_str());
    param.top_k = 1;
    param.top_p = 0.95;
    param.temperature = 0.8;
    param.repeat_penalty = 1.1;
    param.frequency_penalty = 0.0;
    param.presence_penalty = 0.0;
    param.max_new_tokens = 256;
    param.max_context_len = max_context_len;
    param.skip_special_token = true;
    param.extend_param.base_domain_id = 0;
    param.extend_param.embed_flash = 1;

    RKLLMCallback cb = {};
    cb.result_callback = callback;

    int ret = rkllm_init(&g_llm_handle, &param, &cb);
    if (ret != 0) {
        emit_ready("error", "rkllm_init_failed", max_context_len);
        std::cerr << "rkllm_init failed: " << ret << std::endl;
        return 1;
    }
    g_model_load_count = 1;
    emit_ready("ok", "", max_context_len);
    std::cerr << "rkllm resident text server ready pid=" << getpid() << std::endl;

    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty()) {
            continue;
        }
        Request request;
        std::string parse_error;
        if (!parse_request(line, &request, &parse_error)) {
            std::cout
                << "{"
                << "\"type\":\"response\","
                << "\"request_id\":\"\","
                << "\"status\":\"error\","
                << "\"request_index\":" << g_request_count << ","
                << "\"model_load_count\":" << g_model_load_count << ","
                << "\"pid\":" << getpid() << ","
                << "\"first_token_ms\":0,"
                << "\"prefill_ms\":0,"
                << "\"generate_time_ms\":0,"
                << "\"total_time_ms\":0,"
                << "\"decode_tokens_per_s\":0,"
                << "\"prompt_tokens\":0,"
                << "\"output_tokens\":0,"
                << "\"output_text\":\"\","
                << "\"exit_code\":2,"
                << "\"error\":" << json_escape(parse_error)
                << "}\n"
                << std::flush;
            continue;
        }
        if (request.shutdown) {
            std::cout << "{\"type\":\"shutdown\",\"status\":\"ok\"}\n" << std::flush;
            break;
        }
        ++g_request_count;
        auto started = Clock::now();
        ret = run_request(request);
        double total_ms = ms_between(started, g_seen_finish ? g_finish_time : Clock::now());
        emit_response(request, ret, total_ms, ret == 0 ? "" : "rkllm_run_failed");
    }

    cleanup_and_exit(0);
    return 0;
}
