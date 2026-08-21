"""
Robust E2E API test suite for Competitive Programming Judger.
Registers a fresh user, logs in, and submits code for various verdicts.
"""

import asyncio
import httpx
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("e2e_suite")

BASE_URL = os.getenv("API_URL", "http://127.0.0.1:9000")
NON_TERMINAL_STATES = {"PENDING", "QUEUED", "JUDGING", "COMPILING"}

@dataclass
class TestCase:
    name: str
    language: str
    expected_verdict: str
    code: str

class JudgerAPIClient:
    """Encapsulates all API interactions for the test suite."""
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client: Optional[httpx.AsyncClient] = None
        self.token: Optional[str] = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=15.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    def _auth_headers(self) -> dict:
        if not self.token:
            raise ValueError("Not authenticated. Call login() first.")
        return {"Authorization": f"Bearer {self.token}"}

    async def register(self, username: str, email: str, password: str) -> bool:
        try:
            resp = await self.client.post(
                f"{self.base_url}/auth/register",
                json={"username": username, "email": email, "password": password}
            )
            if resp.status_code in (200, 201):
                return True
            logger.error(f"Registration failed ({resp.status_code}): {resp.text}")
            return False
        except httpx.RequestError as e:
            logger.error(f"Network error during registration: {e}")
            return False

    async def login(self, username: str, password: str) -> bool:
        try:
            resp = await self.client.post(
                f"{self.base_url}/auth/login",
                json={"username": username, "password": password}
            )
            if resp.status_code == 200:
                self.token = resp.json().get("access_token")
                return True
            logger.error(f"Login failed ({resp.status_code}): {resp.text}")
            return False
        except httpx.RequestError as e:
            logger.error(f"Network error during login: {e}")
            return False

    async def check_problem(self, problem_id: int) -> bool:
        try:
            resp = await self.client.get(f"{self.base_url}/problems/{problem_id}")
            if resp.status_code == 200:
                title = resp.json().get('title', 'Unknown Title')
                logger.info(f"Problem {problem_id} found: '{title}'")
                return True
            logger.error(f"Problem {problem_id} not found ({resp.status_code})")
            return False
        except httpx.RequestError as e:
            logger.error(f"Network error checking problem: {e}")
            return False

    async def submit_code(self, problem_id: int, language: str, code: str) -> Optional[int]:
        try:
            resp = await self.client.post(
                f"{self.base_url}/submit",
                json={"problem_id": problem_id, "language": language, "src_code": code},
                headers=self._auth_headers()
            )
            if resp.status_code in (200, 201):
                return resp.json().get("submission_id")
            logger.error(f"Submit failed ({resp.status_code}): {resp.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Network error during submission: {e}")
            return None

    async def wait_for_verdict(self, submission_id: int, timeout: int = 90) -> Dict[str, Any]:
        """Polls the API until the submission reaches a terminal state."""
        start_time = time.monotonic()
        
        while time.monotonic() - start_time < timeout:
            try:
                resp = await self.client.get(
                    f"{self.base_url}/submissions/{submission_id}",
                    headers=self._auth_headers()
                )
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("status", "UNKNOWN")
                    
                    if status not in NON_TERMINAL_STATES:
                        return data
                    
                else:
                    logger.warning(f"Failed to fetch status ({resp.status_code}) - Retrying...")
            except httpx.RequestError as e:
                logger.warning(f"Network error while polling (retrying): {e}")

            await asyncio.sleep(2)  # Polling interval
            
        raise asyncio.TimeoutError(f"Timed out after {timeout}s waiting for terminal verdict.")

async def run_test_case(api: JudgerAPIClient, test: TestCase, problem_id: int = 1) -> bool:
    logger.info(f"Running Test: {test.name} [{test.language.upper()}] - Expected: {test.expected_verdict}")
    
    sub_id = await api.submit_code(problem_id, test.language, test.code)
    if not sub_id:
        return False

    logger.info(f"↳ Submission ID {sub_id} created. Waiting for verdict...")

    try:
        result = await api.wait_for_verdict(sub_id, timeout=90)
    except asyncio.TimeoutError as e:
        logger.error(f"↳ ❌ {e}")
        return False

    status = result.get("status", "UNKNOWN")
    time_ms = result.get("execution_time_ms", 0.0)
    mem_mb = result.get("peak_memory_mb", 0.0)

    if status == test.expected_verdict:
        logger.info(f"↳ ✅ PASSED: {status} (time={time_ms}ms, mem={mem_mb}MB)")
        return True
    else:
        logger.error(f"↳ ❌ FAILED: Expected {test.expected_verdict}, got {status}")
        return False

async def main():
    # ── Test Suite Data ──────────────────────────────────────────────────
    tests = [
        TestCase(
            name="C++ Two Sum O(n)",
            language="cpp",
            expected_verdict="AC",
            code=(
                '#include<iostream>\n#include<vector>\n#include<unordered_map>\nusing namespace std;\n'
                'int main(){\n'
                '    int n; cin>>n;\n'
                '    vector<int> nums(n);\n'
                '    for(int&x:nums) cin>>x;\n'
                '    int target; cin>>target;\n'
                '    unordered_map<int,int> seen;\n'
                '    for(int i=0;i<n;i++){\n'
                '        int comp=target-nums[i];\n'
                '        if(seen.count(comp)){cout<<seen[comp]<<" "<<i<<"\\n";return 0;}\n'
                '        seen[nums[i]]=i;\n'
                '    }\n'
                '    return 0;\n'
                '}'
            )
        ),
        TestCase(
            name="C++ Null Pointer Deref",
            language="cpp",
            expected_verdict="RE",
            code='#include<iostream>\nusing namespace std;\nint main(){int*p=nullptr;*p=42;return 0;}'
        ),
        TestCase(
            name="Python Two Sum O(n)",
            language="py",
            expected_verdict="AC",
            code=(
                'n = int(input())\nnums = list(map(int, input().split()))\ntarget = int(input())\n'
                'seen = {}\n'
                'for i, v in enumerate(nums):\n'
                '    comp = target - v\n'
                '    if comp in seen:\n'
                '        print(seen[comp], i)\n'
                '        break\n'
                '    seen[v] = i\n'
            )
        ),
        TestCase(
            name="Python Infinite Loop",
            language="py",
            expected_verdict="TLE",
            code="while True: pass"
        ),
        TestCase(
            name="Java Two Sum O(n)",
            language="java",
            expected_verdict="AC",
            code=(
                'import java.util.*;\n'
                'public class Main {\n'
                '    public static void main(String[] args) {\n'
                '        Scanner sc = new Scanner(System.in);\n'
                '        int n = sc.nextInt();\n'
                '        int[] nums = new int[n];\n'
                '        for (int i = 0; i < n; i++) nums[i] = sc.nextInt();\n'
                '        int target = sc.nextInt();\n'
                '        Map<Integer,Integer> seen = new HashMap<>();\n'
                '        for (int i = 0; i < n; i++) {\n'
                '            int comp = target - nums[i];\n'
                '            if (seen.containsKey(comp)) {\n'
                '                System.out.println(seen.get(comp) + " " + i);\n'
                '                return;\n'
                '            }\n'
                '            seen.put(nums[i], i);\n'
                '        }\n'
                '    }\n'
                '}'
            )
        ),
    ]

    # ── Execution ────────────────────────────────────────────────────────
    suffix = str(uuid.uuid4())[:8]
    username = f"e2e_{suffix}"
    email = f"e2e_{suffix}@test.com"
    password = "TestPass123!"

    async with JudgerAPIClient(BASE_URL) as api:
        logger.info(f"--- Starting E2E Test Suite against {BASE_URL} ---")

        logger.info(f"Registering ephemeral user: {username}")
        if not await api.register(username, email, password):
            return

        logger.info("Logging in...")
        if not await api.login(username, password):
            return

        logger.info("Verifying target problem exists...")
        if not await api.check_problem(1):
            logger.error("Aborting tests because Problem 1 does not exist.")
            return

        print(f"\n{'═'*60}")
        passed_count = 0
        for test in tests:
            if await run_test_case(api, test, problem_id=1):
                passed_count += 1
            print(f"{'─'*60}")

        logger.info(f"Test Suite Completed. Results: {passed_count}/{len(tests)} passed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Test suite aborted by user.")
