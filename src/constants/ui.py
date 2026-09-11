"""UI related constants"""

# Window settings
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 800
WINDOW_PADDING = 20

# Default values
DEFAULT_KTX_DEPARTURE = "서울"
DEFAULT_KTX_ARRIVAL = "부산"

# Time settings
RETRY_DELAY_MIN = 1.0
RETRY_DELAY_MAX = 4.0
CLIENT_RESET_INTERVAL = 500

# Parallel job settings
MAX_CONCURRENT_JOBS = 5  # 동시 "실행 중"(예약 시도 중) 개수 상한 - running_job_count 기준
MAX_SEARCH_JOBS = 5      # 검색 작업 카드(탭) 총 개수 상한 - len(search_jobs) 기준. 실행 여부와 무관하게 탭 자체를 이 이상 만들 수 없다.

# Log settings
LOG_MIN_LINES = 8
LOG_MAX_LINES = 10