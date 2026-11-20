#!/usr/bin/env bash
# Only the video-playlist launchers use this helper. Live camera launchers keep
# their frame cache; a camera cannot seek historical frames in an input video.
configure_event_video_assets() {
  EVENT_DETECTOR_ASSET_ARGS=()
  EVENT_SERVICE_ASSET_ARGS=()
  case "${VLM_ASSET_SOURCE:-video_playlist}" in
    video_playlist)
      if [[ "${VLM_VIDEO_BACKEND:-pyav}" != "indexed" && "${VLM_VIDEO_BACKEND:-pyav}" != "sequential" && "${VLM_VIDEO_BACKEND:-pyav}" != "pyav" ]]; then
        echo "VLM_VIDEO_BACKEND must be pyav, indexed or sequential" >&2
        return 2
      fi
      EVENT_SERVICE_ASSET_ARGS=(
        --asset-source-type video_playlist --asset-source-uri "${PLAYLIST}"
        --asset-playlist-loop
        --asset-video-backend "${VLM_VIDEO_BACKEND:-pyav}"
      )
      ;;
    frame_cache_dir)
      # Explicit compatibility mode; both producer and consumer must change.
      EVENT_DETECTOR_ASSET_ARGS=(
        --frame-cache-dir "${FRAME_CACHE_DIR}"
        --frame-cache-capacity "${FRAME_CACHE_CAPACITY}"
        --frame-cache-jpeg-quality "${FRAME_CACHE_JPEG_QUALITY}"
      )
      EVENT_SERVICE_ASSET_ARGS=(
        --asset-source-type frame_cache_dir --asset-source-uri "${FRAME_CACHE_DIR}"
      )
      ;;
    *)
      echo "VLM_ASSET_SOURCE must be video_playlist or frame_cache_dir" >&2
      return 2
      ;;
  esac
}
