#!/usr/bin/env python3
"""Test AWS credentials auto-detection"""

import asyncio
import aiohttp

BASE_URL = "http://localhost:8080"


async def test_aws_config():
    """Test /v1/config/aws endpoint for auto-detection"""
    async with aiohttp.ClientSession() as session:
        # Test GET /v1/config/aws
        async with session.get(f"{BASE_URL}/v1/config/aws") as resp:
            print(f"Status: {resp.status}")
            data = await resp.json()
            print(f"Response: {data}")

            if data.get("connected"):
                print(f"\n✓ Credentials auto-detected!")
                print(f"  Method: {data.get('method')}")
                if data.get('method') == 'aws_profile':
                    print(f"  Profile: {data.get('profile_name')}")
                if data.get('identity'):
                    print(f"  Account: {data['identity'].get('account')}")
            else:
                print(f"\n✗ No credentials found")
                if data.get('error'):
                    print(f"  Error: {data.get('error')}")


async def test_aws_test_connection():
    """Test /v1/config/aws/test endpoint"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/v1/config/aws/test") as resp:
            print(f"\nTest Connection Status: {resp.status}")
            data = await resp.json()
            print(f"Response: {data}")


if __name__ == "__main__":
    print("Testing AWS credentials auto-detection...\n")
    asyncio.run(test_aws_config())
    asyncio.run(test_aws_test_connection())
