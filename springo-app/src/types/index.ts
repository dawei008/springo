/**
 * Springo TypeScript Type Definitions
 *
 * Comprehensive types for the React+TypeScript rewrite,
 * derived from the legacy vanilla JS app.js and config.js.
 */

// ==================== Content Blocks ====================

export interface TextBlock {
  type: 'text';
  text: string;
}

export interface ImageSource {
  type: 'base64';
  media_type: string;
  data: string;
}

export interface ImageBlock {
  type: 'image';
  source: ImageSource;
  /** Internal-only reference for optimized storage; stripped before API calls */
  _imageRef?: ImageRef;
}

export interface ToolUseBlock {
  type: 'tool_use';
  id: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ToolResultBlock {
  type: 'tool_result';
  tool_use_id: string;
  content: string | ContentBlock[];
  is_error?: boolean;
}

export type ContentBlock = TextBlock | ImageBlock | ToolUseBlock | ToolResultBlock;

// ==================== Tool Use (runtime tracking) ====================

export interface ToolUse {
  id: string;
  name: string;
  input: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  status?: 'running' | 'complete' | 'error';
  elapsed?: number;
}

// ==================== Messages ====================

export interface Message {
  role: 'user' | 'assistant';
  content: string | ContentBlock[];
  timestamp?: number;
  /** Pre-rendered display content (markdown HTML) */
  displayContent?: string;
  /** Whether the assistant message contains tool_use blocks */
  hasToolUse?: boolean;
  /** Result of a delegated sub-task */
  isDelegationResult?: boolean;
  /** Result of an agent-team task */
  isTaskResult?: boolean;
  /** Thinking indicator placeholder */
  isThinking?: boolean;
  /** Content merged from multiple streaming chunks */
  mergedContent?: string;
  /** Runtime tool uses with live status/result (from SSE streaming) */
  toolUses?: ToolUse[];
  /** Team ask_user question with clickable options */
  askUser?: {
    teamId: string;
    agentName: string;
    options: Array<{ label: string; description?: string }>;
  };
  /** Marks a team→user chat message (should not be overwritten by streaming updates) */
  _teamChat?: boolean;
}

// ==================== Image References ====================

export interface ImageRef {
  session_id: string;
  relative_path: string;
}

// ==================== Attachments ====================

export interface Attachment {
  name: string;
  type: string;
  data?: string;
  path?: string;
  imageRef?: ImageRef;
}

// ==================== Sessions / Conversations ====================

export type ConversationStatus = 'idle' | 'running' | 'completed' | 'error' | 'compacting';

/** Alias used by session store */
export type SessionStatus = ConversationStatus;

export type SessionMode = 'general' | 'design' | 'plan' | 'team' | 'meeting' | 'recording' | 'novel';

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  status: ConversationStatus;
  workingDir: string;
  isCustomTitle: boolean;
  mode?: SessionMode;
  messages: Message[];
  todos?: TodoItem[];
}

/** Alias used by session store */
export type Session = Conversation;

export interface TodoItem {
  id: string;
  text: string;
  done: boolean;
}

// ==================== Per-Conversation Runtime ====================

export interface DelegatedTask {
  targetConvId: string;
  status: 'pending' | 'running' | 'complete' | 'error';
  result?: string;
}

export interface IncomingTask {
  sourceConvId: string;
  prompt: string;
  status: 'pending' | 'running' | 'complete' | 'error';
}

export interface ConvRuntime {
  isStreaming: boolean;
  attachments: Attachment[];
  messages: Message[];
  delegatedTasks: Record<string, DelegatedTask>;
  incomingTasks: Record<string, IncomingTask>;
  delegationQueue: string[];
  todos: TodoItem[];
  wasStopped?: boolean;
}

// ==================== UI State Types ====================

export interface ToolPanelState {
  toolUses: ToolUse[];
  completedCount: number;
  runningCount: number;
  allComplete: boolean;
}

export interface Toast {
  message: string;
  type: 'info' | 'success' | 'warning' | 'error';
  duration: number;
}

export interface ActiveSkill {
  name: string;
  title?: string;
  description?: string;
}

// ==================== Settings ====================

export interface Settings {
  model?: string;
  maxTokens?: number;
  temperature?: number;
  systemPrompt?: string;
  /** Compact model used for context summarization */
  compactModel?: string;
  [key: string]: unknown;
}

// ==================== SSE Events ====================

/** Raw SSE frame from parseSSEStream */
export interface SSEFrame {
  event: string;
  data: unknown;
}

// --- Individual SSE event payloads ---

export interface MessageStartEvent {
  message: {
    id: string;
    type: string;
    role: string;
    model: string;
  };
}

export interface ContentBlockStartEvent {
  index: number;
  content_block: {
    type: 'text' | 'tool_use';
    id?: string;
    name?: string;
    text?: string;
  };
}

export interface TextDelta {
  type: 'text_delta';
  text: string;
}

export interface InputJsonDelta {
  type: 'input_json_delta';
  partial_json: string;
}

export interface ContentBlockDeltaEvent {
  index: number;
  delta: TextDelta | InputJsonDelta;
}

export interface ContentBlockStopEvent {
  index: number;
}

export interface MessageStopEvent {
  stop_reason?: string;
}

export interface ToolExecutionStartEvent {
  tools: Array<{ id: string; name: string; input?: Record<string, unknown> }>;
}

export interface ToolExecutingEvent {
  id: string;
  name: string;
}

export interface ToolResultEvent {
  tool_use_id: string;
  tool_name: string;
  result: Record<string, unknown>;
}

export interface HeartbeatEvent {
  tool_id: string;
  tool_name: string;
  elapsed_seconds: number;
}

export interface ToolExecutionCompleteEvent {
  count: number;
}

export interface SkillInjectedEvent {
  skill_name: string;
}

export interface ContextCompactEvent {
  reason: string;
  tokens_before: number;
}

export interface ContextCompactDoneEvent {
  messages_before: number;
  messages_after: number;
  tokens_after: number;
}

export interface ContextCompactFailedEvent {
  error: string;
}

export interface MessagesUpdatedEvent {
  messages: Message[];
  token_count: number;
}

// --- Team events ---

export interface TeamSpawnedEvent {
  team_id: string;
  agents: TeamAgent[];
  user_request: string;
}

export interface TeamAgent {
  agent_id?: string;
  name?: string;
  role: string;
  purpose?: string;
}

export interface TeamPlanningEvent {
  team_id: string;
}

export interface TeamTaskBoardEvent {
  team_id: string;
  tasks: TeamTask[];
}

export interface TeamTask {
  id: string;
  title: string;
  owner?: string;
  status: 'pending' | 'in_progress' | 'completed' | 'error' | 'unblocked';
  blockedBy?: string[];
}

export interface TeamAgentStartEvent {
  team_id: string;
  agent_id: string;
  role: string;
  task_title: string;
  agent_name?: string;
}

export interface TeamAgentProgressEvent {
  team_id: string;
  agent_id: string;
  role: string;
  status: string;
  preview?: string;
}

export interface TeamAgentCompleteEvent {
  team_id: string;
  agent_id: string;
  role: string;
  task_title: string;
  findings: string;
}

export interface TeamAgentErrorEvent {
  team_id: string;
  agent_id: string;
  role: string;
  error: string;
}

export interface TeamAgentDeltaEvent {
  team_id: string;
  agent_id: string;
  role: string;
  delta: string;
}

export interface TeamAgentToolEvent {
  team_id: string;
  agent_id: string;
  role: string;
  tool_name: string;
  status: string;
  result_preview?: string;
}

export interface TeamSynthesisDeltaEvent {
  delta: string;
}

export interface TeamSynthesizingEvent {
  team_id: string;
}

export interface TeamCompleteEvent {
  team_id: string;
  result?: string;
}

export interface TeamErrorEvent {
  team_id: string;
  error: string;
}

export interface TeamAgentMessageEvent {
  team_id: string;
  sender: string;
  recipient: string;
  content: string;
  summary?: string;
}

export interface TeamAgentBroadcastEvent {
  team_id: string;
  sender: string;
  content: string;
  summary?: string;
}

export interface TeamAgentIdleEvent {
  team_id: string;
  agent_name: string;
  peer_dm_summary?: string;
}

export interface TeamAskUserEvent {
  team_id: string;
  agent_name: string;
  question: string;
  options: Array<{ label: string; description?: string }>;
}

export interface TeamAgentShutdownEvent {
  team_id: string;
  agent_name: string;
}

export interface TeamTaskCreatedEvent {
  team_id: string;
  task_id: string;
  title: string;
  owner?: string;
}

export interface TeamTaskUpdatedEvent {
  team_id: string;
  task_id: string;
  status: string;
  owner?: string;
  title?: string;
}

export interface TeamTaskUnblockedEvent {
  team_id: string;
  task_id: string;
  owner?: string;
  title?: string;
}

export interface SSEErrorEvent {
  error?: { message: string; type?: string };
}

/** Discriminated union of all SSE event types */
export type SSEEventType =
  | 'message_start'
  | 'content_block_start'
  | 'content_block_delta'
  | 'content_block_stop'
  | 'message_stop'
  | 'tool_execution_start'
  | 'tool_start'
  | 'tool_executing'
  | 'tool_result'
  | 'heartbeat'
  | 'tool_execution_complete'
  | 'skill_injected'
  | 'context_compact'
  | 'context_compact_done'
  | 'context_compact_failed'
  | 'messages_updated'
  | 'team_spawned'
  | 'team_planning'
  | 'team_task_board'
  | 'team_agent_start'
  | 'team_agent_progress'
  | 'team_agent_complete'
  | 'team_agent_error'
  | 'team_agent_delta'
  | 'team_agent_tool'
  | 'team_synthesis_delta'
  | 'team_synthesizing'
  | 'team_complete'
  | 'team_error'
  | 'team_agent_message'
  | 'team_agent_broadcast'
  | 'team_ask_user'
  | 'team_agent_idle'
  | 'team_agent_shutdown'
  | 'team_task_created'
  | 'team_task_updated'
  | 'team_task_unblocked'
  | 'message_delta'
  | 'error';

// ==================== API Request / Response Shapes ====================

export interface MessageRequest {
  model: string;
  messages: Array<{ role: string; content: string | ContentBlock[] }>;
  max_tokens?: number;
  temperature?: number;
  stream?: boolean;
  system?: string;
  tools?: ToolDefinition[];
}

export interface MessageAutoRequest extends MessageRequest {
  session_id?: string;
  max_tool_iterations?: number;
  compact_model?: string;
}

export interface ToolDefinition {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface MessageResponse {
  id: string;
  type: 'message';
  role: 'assistant';
  content: ContentBlock[];
  model: string;
  stop_reason: string | null;
  stop_sequence: string | null;
  usage: Usage;
}

export interface Usage {
  input_tokens: number;
  output_tokens: number;
}

export interface UsageData {
  input_tokens: number;
  output_tokens: number;
  cache_creation_input_tokens: number;
  cache_read_input_tokens: number;
}

// ==================== Session API shapes ====================

export interface SessionMetadata {
  title?: string;
  createdAt?: number;
  updatedAt?: number;
  workingDir?: string;
  isCustomTitle?: boolean;
  [key: string]: unknown;
}

export interface SessionListItem {
  session_id: string;
  id?: string;
  title?: string;
  modified?: string;
  createdAt?: number;
  workingDir?: string;
  metadata?: SessionMetadata;
}

export interface SessionDetail {
  session_id: string;
  messages: Message[];
  metadata?: SessionMetadata;
}

// ==================== Tool API shapes ====================

export interface ToolInfo {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  server?: string;
}

export interface ToolExecuteRequest {
  name: string;
  input: Record<string, unknown>;
}

export interface ToolExecuteResponse {
  result: Record<string, unknown>;
}

// ==================== Skill API shapes ====================

export interface Skill {
  name: string;
  title: string;
  description: string;
  keywords?: string[];
  path?: string;
}

// ==================== Config API shapes ====================

export interface WorkingDirConfig {
  working_dir: string;
}

export interface AWSConfig {
  region?: string;
  profile?: string;
  access_key_id?: string;
  secret_access_key?: string;
}

export interface S3Config {
  enabled?: boolean;
  bucket?: string;
  prefix?: string;
}

export interface MemoryConfig {
  enabled?: boolean;
  agent_id?: string;
  alias_id?: string;
  region?: string;
}

export interface FeishuConfig {
  app_id?: string;
  app_secret?: string;
  enabled?: boolean;
}

export interface VendorKeysConfig {
  [vendor: string]: string;
}

// ==================== Model Registry ====================

export interface ModelContextLimits {
  max_context_tokens: number;
  compact_threshold: number;
  warning_threshold: number;
  target_after_summary: number;
  max_output_tokens: number;
}

export interface Model {
  id: string;
  object: string;
  created: number;
  vendor: string;
  bedrock_model_id: string;
  display_name: string;
  provider: string;
  context_window: number;
  max_output: number;
  supports_vision: boolean;
  supports_thinking: boolean;
  api_format: string;
  supports_extended_context: boolean;
  context: ModelContextLimits;
  context_standard: ModelContextLimits | null;
}

/** Simpler model info shape (subset used in some API responses) */
export interface ModelInfo {
  id: string;
  name: string;
  vendor: string;
  vendor_model_id: string;
  max_tokens?: number;
  context_window?: number;
  supports_vision?: boolean;
  supports_tools?: boolean;
}

// ==================== Team API shapes ====================

export interface TeamSpawnRequest {
  user_request: string;
  model?: string;
  session_id?: string;
  team_type?: 'split' | 'collaborative';
  agents?: Array<{ name: string; role: string }>;
}

export interface TeamInfo {
  team_id: string;
  status: string;
  agents: TeamAgent[];
  created_at?: string;
}

export interface TeamMessageRequest {
  content: string;
  sender?: string;
}

// ==================== Context API shapes ====================

export interface ContextItem {
  type: string;
  content: string;
  source?: string;
  added_at?: string;
}

export interface ContextStats {
  total_tokens: number;
  max_tokens: number;
  usage_percent: number;
  status: 'normal' | 'warning' | 'critical';
}

// ==================== Image API shapes ====================

export interface ImageUploadResponse {
  url: string;
  session_id: string;
  filename: string;
}

export interface ImageGenerateRequest {
  prompt: string;
  model?: string;
  width?: number;
  height?: number;
}

// ==================== Terminal API shapes ====================

export interface TerminalExecuteRequest {
  command: string;
  working_dir?: string;
  timeout?: number;
}

export interface TerminalExecuteResponse {
  stdout: string;
  stderr: string;
  exit_code: number;
}

// ==================== Health ====================

export interface HealthResponse {
  status: string;
  version?: string;
  uptime?: number;
}

// ==================== Config Constants (from config.js) ====================

export interface TokenLimits {
  MAX_CONTEXT: number;
  WARNING_THRESHOLD: number;
  COMPACT_THRESHOLD: number;
  MAX_OUTPUT: number;
}

export interface Timeouts {
  API_DEFAULT: number;
  FETCH_RETRY: number;
  STREAMING: number;
  SSE_HEARTBEAT: number;
  TOOL_EXECUTION: number;
  TOOL_EXECUTION_LONG: number;
  BACKGROUND_TASK_MAX: number;
  HEALTH_CHECK: number;
  MEMORY_SYNC: number;
  TOAST_DURATION: number;
  STATUS_RESET: number;
  ANIMATION: number;
  SCROLL_DELAY: number;
}

export interface RetryConfig {
  MAX_ATTEMPTS: number;
  BACKOFF_MAX: number;
}

export interface FeatureFlags {
  AUTO_TOOL_EXECUTION: boolean;
  MEMORY_SYNC: boolean;
  S3_SYNC: boolean;
}

export interface AppConfig {
  TOKENS: TokenLimits;
  TIMEOUTS: Timeouts;
  RETRY: RetryConfig;
  FEATURES: FeatureFlags;
}

export const CONFIG: AppConfig = {
  TOKENS: {
    MAX_CONTEXT: 200_000,
    WARNING_THRESHOLD: 160_000,
    COMPACT_THRESHOLD: 120_000,
    MAX_OUTPUT: 64_000,
  },
  TIMEOUTS: {
    API_DEFAULT: 60_000,
    FETCH_RETRY: 300_000,
    STREAMING: 900_000,
    SSE_HEARTBEAT: 300_000,
    TOOL_EXECUTION: 300_000,
    TOOL_EXECUTION_LONG: 600_000,
    BACKGROUND_TASK_MAX: 3_600_000,
    HEALTH_CHECK: 30_000,
    MEMORY_SYNC: 10_000,
    TOAST_DURATION: 5_000,
    STATUS_RESET: 2_000,
    ANIMATION: 300,
    SCROLL_DELAY: 50,
  },
  RETRY: {
    MAX_ATTEMPTS: 3,
    BACKOFF_MAX: 5_000,
  },
  FEATURES: {
    AUTO_TOOL_EXECUTION: true,
    MEMORY_SYNC: true,
    S3_SYNC: true,
  },
};

/** Skill auto-detection keyword map */
export const SKILL_KEYWORDS: Record<string, string[]> = {
  pptx: ['ppt', 'pptx', '幻灯片', '演示文稿', 'powerpoint', 'presentation', 'slides'],
  docx: ['docx', 'word', '文档', 'document', '报告'],
  xlsx: ['xlsx', 'excel', '表格', 'spreadsheet', '电子表格', '数据分析'],
  pdf: ['pdf', '填表', 'form', '表单填写'],
};

/** Media-type / extension mappings */
export const MEDIA_TYPE_TO_EXT: Record<string, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/gif': 'gif',
  'image/webp': 'webp',
};

export const EXT_TO_MEDIA_TYPE: Record<string, string> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  gif: 'image/gif',
  webp: 'image/webp',
};

// ======================== Design Element Interaction ========================

export interface SelectedElement {
  tagName: string;
  id?: string;
  className?: string;
  textPreview?: string;
  rect: { x: number; y: number; width: number; height: number };
  cssPath: string;
  computedStyles?: Record<string, string>;
}

export interface DesignError {
  type: 'runtime' | 'console' | 'render';
  message: string;
  source?: string;
  line?: number;
  timestamp: number;
}

// ======================== Design System ========================

export interface DesignSystemSource {
  companyBlurb: string;
  githubLinks: string[];
  notes: string;
  codeFileNames: string[];
  assetFileNames: string[];
}

export interface DesignSystemConfig {
  id?: string;
  colors: Record<string, string>;
  fonts: { heading: string; body: string };
  components: string[];
  brandName?: string;
  sourceDir?: string;
  raw?: string;
  published?: boolean;
  isDefault?: boolean;
  createdAt?: number;
  updatedAt?: number;
  author?: string;
  source?: DesignSystemSource;
}

// ======================== Plan Mode ========================

export interface PlanSection {
  id: string;
  title: string;
  description: string;
  steps: string[];
  dependencies?: string[];
  risks?: string[];
  effort?: 'low' | 'medium' | 'high';
  validation?: string;
  status: 'pending' | 'approved' | 'rejected' | 'in_progress' | 'completed' | 'failed';
  feedback?: string | null;
  result?: string | null;
}

export interface PlanStructure {
  id: string;
  title: string;
  summary: string;
  analysis?: string;
  sections: PlanSection[];
  status: 'draft' | 'reviewing' | 'approved' | 'executing' | 'completed' | 'failed';
  created_at: string;
  updated_at: string;
  session_id?: string;
}
