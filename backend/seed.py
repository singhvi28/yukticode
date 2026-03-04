import asyncio
import os
import io
import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from server.db.database import Base
from server.db.models import User, Problem, ProblemVersion
from server.config import DATABASE_URL
from server.blob_storage import client, ensure_bucket_exists, upload_text
from server.auth import get_password_hash

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

two_sum_md = """# Two Sum

Given an array of integers `nums` and an integer `target`, return *indices of the two numbers such that they add up to `target`*.

You may assume that each input would have **exactly one solution**, and you may not use the *same* element twice.

You can return the answer in any order.

### Example 1:
```
Input: nums = [2,7,11,15], target = 9
Output: [0,1]
Explanation: Because nums[0] + nums[1] == 9, we return [0, 1].
```

### Constraints:
* `2 <= nums.length <= 10^4`
* `-10^9 <= nums[i] <= 10^9`
* `-10^9 <= target <= 10^9`
"""

valid_palindrome_md = """# Valid Palindrome

A phrase is a **palindrome** if, after converting all uppercase letters into lowercase letters and removing all non-alphanumeric characters, it reads the same forward and backward. Alphanumeric characters include letters and numbers.

Given a string `s`, return `true` if it is a **palindrome**, or `false` otherwise.

### Example 1:
```
Input: s = "A man, a plan, a canal: Panama"
Output: true
Explanation: "amanaplanacanalpanama" is a palindrome.
```
"""

async def seed():
    # 1. Ensure MinIO Buckets exist
    ensure_bucket_exists("problems")
    ensure_bucket_exists("submissions")
    
    # 2. Recreate Tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        
    # 3. Populate Database
    async with async_session() as db:
        admin_user = User(
            username="admin",
            email="admin@yukticode.com",
            hashed_password=get_password_hash("password"),
            is_admin=True
        )
        db.add(admin_user)
        await db.commit()
        await db.refresh(admin_user)
        
        # Upload Two Sum markdown
        ts_url = upload_text("problems", "two_sum.md", two_sum_md)
        p1 = Problem(title="Two Sum", author_id=admin_user.id, is_published=True)
        db.add(p1)
        await db.commit()
        await db.refresh(p1)
        
        pv1 = ProblemVersion(
            problem_id=p1.id, version_number=1,
            statement_url=ts_url,
            time_limit_ms=2000, memory_limit_mb=256,
            test_data_path="/test_data/two_sum"
        )
        db.add(pv1)
        
        # Upload Valid Palindrome markdown
        vp_url = upload_text("problems", "valid_palindrome.md", valid_palindrome_md)
        p2 = Problem(title="Valid Palindrome", author_id=admin_user.id, is_published=True)
        db.add(p2)
        await db.commit()
        await db.refresh(p2)
        
        pv2 = ProblemVersion(
            problem_id=p2.id, version_number=1,
            statement_url=vp_url,
            time_limit_ms=1000, memory_limit_mb=256,
            test_data_path="/test_data/valid_palindrome"
        )
        db.add(pv2)
        
        await db.commit()
        print("Database seeded with admin user, Two Sum, and Valid Palindrome!")

if __name__ == "__main__":
    asyncio.run(seed())
