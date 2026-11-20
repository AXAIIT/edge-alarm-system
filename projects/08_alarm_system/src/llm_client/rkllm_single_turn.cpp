#include <chrono>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

#include "rkllm.h"

using Clock = std::chrono::steady_clock;

static LLMHandle g_llm_handle = nullptr;
static std::string g_output;
static Clock::time_point g_run_start;
static Clock::time_point g_first_token_time;
static Clock::time_point g_finish_time;
static bool g_seen_first_token = false;
static bool g_seen_finish = false;

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

static void usage(const char* argv0) {
    std::cerr << "Usage: " << argv0
              << " --model <model.rkllm> --prompt <text> --max-output-tokens <n>"
              << " --max-context-len <n> [--metrics-json <path>]\n";
}

int main(int argc, char** argv) {
    std::signal(SIGINT, [](int) { cleanup_and_exit(130); });
    std::signal(SIGTERM, [](int) { cleanup_and_exit(143); });

    std::string model;
    std::string prompt;
    std::string metrics_json;
    int max_output_tokens = 160;
    int max_context_len = 2048;

    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if (arg == "--model" && i + 1 < argc) {
            model = argv[++i];
        } else if (arg == "--prompt" && i + 1 < argc) {
            prompt = argv[++i];
        } else if (arg == "--max-output-tokens" && i + 1 < argc) {
            max_output_tokens = std::atoi(argv[++i]);
        } else if (arg == "--max-context-len" && i + 1 < argc) {
            max_context_len = std::atoi(argv[++i]);
        } else if (arg == "--metrics-json" && i + 1 < argc) {
            metrics_json = argv[++i];
        } else {
            usage(argv[0]);
            return 2;
        }
    }

    if (prompt.empty()) {
        std::getline(std::cin, prompt);
    }
    if (model.empty() || prompt.empty()) {
        usage(argv[0]);
        return 2;
    }

    auto total_start = Clock::now();
    RKLLMParam param = rkllm_createDefaultParam();
    param.model_path = const_cast<char*>(model.c_str());
    param.top_k = 1;
    param.top_p = 0.95;
    param.temperature = 0.8;
    param.repeat_penalty = 1.1;
    param.frequency_penalty = 0.0;
    param.presence_penalty = 0.0;
    param.max_new_tokens = max_output_tokens;
    param.max_context_len = max_context_len;
    param.skip_special_token = true;
    param.extend_param.base_domain_id = 0;
    param.extend_param.embed_flash = 1;

    RKLLMCallback cb = {};
    cb.result_callback = callback;

    auto load_start = Clock::now();
    int ret = rkllm_init(&g_llm_handle, &param, &cb);
    auto load_end = Clock::now();
    if (ret != 0) {
        std::cerr << "rkllm_init failed: " << ret << "\n";
        return 1;
    }

    RKLLMInput input;
    std::memset(&input, 0, sizeof(input));
    input.input_type = RKLLM_INPUT_PROMPT;
    input.role = const_cast<char*>("user");
    input.prompt_input = const_cast<char*>(prompt.c_str());

    RKLLMInferParam infer;
    std::memset(&infer, 0, sizeof(infer));
    infer.mode = RKLLM_INFER_GENERATE;
    infer.keep_history = 0;

    g_run_start = Clock::now();
    ret = rkllm_run(g_llm_handle, &input, &infer, nullptr);
    auto run_end = g_seen_finish ? g_finish_time : Clock::now();
    auto total_end = Clock::now();

    if (g_llm_handle != nullptr) {
        rkllm_destroy(g_llm_handle);
        g_llm_handle = nullptr;
    }

    std::cout << g_output << std::flush;

    int output_tokens = approx_tokens(g_output);
    double load_time_s = ms_between(load_start, load_end) / 1000.0;
    double first_token_ms = g_seen_first_token ? ms_between(g_run_start, g_first_token_time) : 0.0;
    double generate_ms = ms_between(g_run_start, run_end);
    double total_ms = ms_between(total_start, total_end);
    double decode_tps = 0.0;
    if (output_tokens > 1 && generate_ms > first_token_ms) {
        decode_tps = (output_tokens - 1) / ((generate_ms - first_token_ms) / 1000.0);
    }

    if (!metrics_json.empty()) {
        std::ofstream f(metrics_json);
        f << "{\n"
          << "  \"load_time_s\": " << load_time_s << ",\n"
          << "  \"prefill_time_ms\": " << first_token_ms << ",\n"
          << "  \"prefill_tokens\": " << approx_tokens(prompt) << ",\n"
          << "  \"first_token_latency_ms\": " << first_token_ms << ",\n"
          << "  \"generate_time_ms\": " << generate_ms << ",\n"
          << "  \"total_time_ms\": " << total_ms << ",\n"
          << "  \"decode_tokens_per_s\": " << decode_tps << ",\n"
          << "  \"prompt_tokens\": " << approx_tokens(prompt) << ",\n"
          << "  \"output_tokens\": " << output_tokens << ",\n"
          << "  \"memory_peak_mb\": 0,\n"
          << "  \"output_text\": " << json_escape(g_output) << ",\n"
          << "  \"status\": " << json_escape(ret == 0 ? "ok" : "failed") << ",\n"
          << "  \"exit_code\": " << ret << ",\n"
          << "  \"timed_out\": false,\n"
          << "  \"error\": " << json_escape(ret == 0 ? "" : "rkllm_run_failed") << "\n"
          << "}\n";
    }

    return ret == 0 ? 0 : 1;
}
