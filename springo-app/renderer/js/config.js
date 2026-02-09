/**
 * Springo Configuration Constants
 * Centralized configuration for the entire application
 */

// API Base URL - for Electron app
const BASE_URL = 'http://127.0.0.1:8081';

// Configuration constants - centralized magic numbers
const CONFIG = {
    // Token limits
    TOKENS: {
        MAX_CONTEXT: 200000,        // Claude context window
        WARNING_THRESHOLD: 160000,  // Show warning at 80%
        COMPACT_THRESHOLD: 120000,  // Trigger compaction at 60%
        MAX_OUTPUT: 64000           // Max tokens for response
    },
    // Timeouts (in milliseconds) - aligned with backend config.py
    TIMEOUTS: {
        API_DEFAULT: 60000,         // 60s for normal API calls
        FETCH_RETRY: 300000,        // 5 min for fetch with retry
        STREAMING: 900000,          // 15 min for streaming (matches bedrock_read_timeout=900s)
        SSE_HEARTBEAT: 300000,      // 5 min SSE heartbeat timeout (covers context compaction gaps between iterations)
        TOOL_EXECUTION: 300000,     // 5 min per tool execution (matches tool_execution_timeout=300s)
        TOOL_EXECUTION_LONG: 600000,// 10 min for long tasks (builds, installs)
        BACKGROUND_TASK_MAX: 3600000,// 1 hour max for background tasks
        HEALTH_CHECK: 30000,        // 30s between health checks
        MEMORY_SYNC: 10000,         // 10s between memory sync checks
        TOAST_DURATION: 5000,       // Toast notification duration
        STATUS_RESET: 2000,         // Status bar reset delay
        ANIMATION: 300,             // UI animations
        SCROLL_DELAY: 50            // Scroll animation delay
    },
    // Retry settings
    RETRY: {
        MAX_ATTEMPTS: 3,
        BACKOFF_MAX: 5000
    },
    // Feature flags
    FEATURES: {
        AUTO_TOOL_EXECUTION: true,  // Server-side tool execution
        MEMORY_SYNC: true,          // AgentCore Memory sync
        S3_SYNC: true               // S3 session sync
    }
};

// Skill keywords for auto-detection
const SKILL_KEYWORDS = {
    'pptx': ['ppt', 'pptx', '幻灯片', '演示文稿', 'powerpoint', 'presentation', 'slides'],
    'docx': ['docx', 'word', '文档', 'document', '报告'],
    'xlsx': ['xlsx', 'excel', '表格', 'spreadsheet', '电子表格', '数据分析'],
    'pdf': ['pdf', '填表', 'form', '表单填写'],
};

// Image media type mappings
const MEDIA_TYPE_TO_EXT = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/gif': 'gif',
    'image/webp': 'webp'
};

const EXT_TO_MEDIA_TYPE = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'webp': 'image/webp'
};
