import httpx
import asyncio

async def test_flow():
    base_url = "http://127.0.0.1:9000"
    
    async with httpx.AsyncClient() as client:
        # 0. Register
        print("Registering...")
        reg_payload = {"username": "akkisinghvi28", "email": "akkisinghvi28@gmail.com", "password": "yoyoboy123"}
        await client.post(f"{base_url}/auth/register", json=reg_payload)

        # 1. Login
        print("Logging in...")
        resp = await client.post(f"{base_url}/auth/login", json={"username": "akkisinghvi28", "password": "yoyoboy123"})
        if resp.status_code != 200:
            print("Login failed:", resp.text)
            return
            
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("Login successful.")

        # 2. Submit solution for Two Sum (problem_id 1)
        print("Submitting solution...")
        payload = {
            "problem_id": 1,
            "language": "py",
            "src_code": "def twoSum(nums, target):\n    return []"
        }
        resp = await client.post(f"{base_url}/submit", json=payload, headers=headers)
        if resp.status_code != 200:
            print("Submit failed:", resp.text)
            return
            
        print("Submit response:", resp.json())
        sub_id = resp.json().get("submission_id")
        
        # 3. Poll for status
        for _ in range(5):
            await asyncio.sleep(2)
            resp = await client.get(f"{base_url}/submissions/{sub_id}", headers=headers)
            print("Status:", resp.json())

asyncio.run(test_flow())
