#!/usr/bin/env python3
"""
测试错误处理模块
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from error_handler import (
    parse_error,
    format_error_response,
    get_user_friendly_message,
    should_retry,
    get_http_status,
    ErrorCategory
)


def test_error_parsing():
    """测试错误解析"""
    print("=" * 60)
    print("错误处理模块测试")
    print("=" * 60)

    test_cases = [
        # (错误消息, 期望的错误代码, 期望的类别)
        # Claude API 错误
        ("ThrottlingException: Rate exceeded", "throttling", ErrorCategory.RATE_LIMIT),
        ("ValidationException: Invalid message format", "validation_error", ErrorCategory.VALIDATION),
        ("AccessDeniedException: Access denied", "access_denied", ErrorCategory.AUTH),
        ("ServiceUnavailableException: Service busy", "service_unavailable", ErrorCategory.SERVICE),
        ("Too many tokens in request", "too_many_tokens", ErrorCategory.RATE_LIMIT),
        ("rate limit exceeded", "rate_limit", ErrorCategory.RATE_LIMIT),
        ("Connection refused", "connection_error", ErrorCategory.NETWORK),
        ("timeout error", "timeout", ErrorCategory.TIMEOUT),
        ("overloaded_error: API overloaded", "overloaded", ErrorCategory.SERVICE),
        ("context length exceeded", "context_length_exceeded", ErrorCategory.CONTENT),
        # Springo 客户端错误
        ("Access denied: /etc/passwd is outside allowed directories", "access_denied_path", ErrorCategory.PERMISSION),
        ("File not found: /tmp/nonexistent.txt", "file_not_found", ErrorCategory.VALIDATION),
        ("Directory not found: /tmp/nodir", "directory_not_found", ErrorCategory.VALIDATION),
        ("Not a file: /tmp", "not_a_file", ErrorCategory.VALIDATION),
        ("File too large (2MB). Maximum is 1MB.", "file_too_large", ErrorCategory.VALIDATION),
        ("Command blocked for safety reasons", "command_blocked", ErrorCategory.PERMISSION),
        ("Command timed out after 60 seconds", "command_timeout", ErrorCategory.TIMEOUT),
        ("Not a git repository", "not_git_repo", ErrorCategory.VALIDATION),
        ("Git command timed out", "git_timeout", ErrorCategory.TIMEOUT),
        ("No files specified", "no_files_specified", ErrorCategory.VALIDATION),
        ("Commit message is required", "commit_message_required", ErrorCategory.VALIDATION),
        ("Unknown tool: fake_tool", "unknown_tool", ErrorCategory.VALIDATION),
        ("Tool call incomplete: missing params", "tool_call_incomplete", ErrorCategory.VALIDATION),
        # 未知错误
        ("Unknown error message", "unknown_error", ErrorCategory.UNKNOWN),
    ]

    passed = 0
    failed = 0

    print("\n[1] 错误解析测试:")
    for error_msg, expected_code, expected_category in test_cases:
        error = Exception(error_msg)
        parsed = parse_error(error)

        code_match = parsed.code == expected_code
        category_match = parsed.category == expected_category

        if code_match and category_match:
            print(f"    ✅ '{error_msg[:40]}...' -> {parsed.code}")
            passed += 1
        else:
            print(f"    ❌ '{error_msg[:40]}...'")
            print(f"       期望: {expected_code}, {expected_category}")
            print(f"       实际: {parsed.code}, {parsed.category}")
            failed += 1

    print(f"\n    结果: {passed} 通过, {failed} 失败")

    # 测试错误响应格式化
    print("\n[2] 错误响应格式化测试:")
    error = Exception("ThrottlingException: Rate exceeded")
    response = format_error_response(error, lang="zh")

    assert response["type"] == "error", "响应类型应为 error"
    assert "error" in response, "响应应包含 error 字段"
    assert "message" in response["error"], "error 应包含 message"
    assert "suggestion" in response["error"], "error 应包含 suggestion"
    print(f"    ✅ 响应格式正确")
    print(f"       type: {response['error']['type']}")
    print(f"       code: {response['error']['code']}")
    print(f"       message: {response['error']['message'][:50]}...")

    # 测试重试判断
    print("\n[3] 重试判断测试:")
    retry_tests = [
        ("ThrottlingException", True),
        ("ValidationException", False),
        ("ServiceUnavailableException", True),
        ("AccessDeniedException", False),
        ("TimeoutError", True),
    ]

    for error_msg, should_retry_expected in retry_tests:
        error = Exception(error_msg)
        retry, wait_time = should_retry(error)
        status = "✅" if retry == should_retry_expected else "❌"
        print(f"    {status} {error_msg}: 应重试={should_retry_expected}, 实际={retry}, 等待={wait_time}s")

    # 测试 HTTP 状态码
    print("\n[4] HTTP 状态码测试:")
    status_tests = [
        ("ThrottlingException", 429),
        ("ValidationException", 400),
        ("AccessDeniedException", 403),
        ("ServiceUnavailableException", 503),
    ]

    for error_msg, expected_status in status_tests:
        error = Exception(error_msg)
        actual_status = get_http_status(error)
        status = "✅" if actual_status == expected_status else "❌"
        print(f"    {status} {error_msg}: 期望={expected_status}, 实际={actual_status}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = test_error_parsing()
    exit(0 if success else 1)
