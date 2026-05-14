import asyncio
import json

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from server.db.database import Base
from server.db.models import User, Problem, TestCase
from server.config import DATABASE_URL
from server.auth import get_password_hash

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# ---------------------------------------------------------------------------
# Problem statements (markdown stored in Postgres)
# ---------------------------------------------------------------------------

TWO_SUM_MD = """# Two Sum

Given an array of integers `nums` and an integer `target`, return indices of the two numbers such that they add up to `target`.

You may assume that each input has **exactly one solution**, and you may not use the same element twice.

You can return the answer in any order. Print the two indices separated by a space.

### Input Format
```
n
a1 a2 ... an
target
```

### Output Format
```
i j
```

### Example 1
```
Input:
4
2 7 11 15
9

Output:
0 1
```

### Constraints
- `2 <= n <= 10^4`
- `-10^9 <= ai, target <= 10^9`
"""

VALID_PALINDROME_MD = """# Valid Palindrome

A phrase is a **palindrome** if, after converting all uppercase letters into lowercase letters and removing all non-alphanumeric characters, it reads the same forward and backward.

Given a string `s`, print `true` if it is a palindrome, or `false` otherwise.

### Input Format
A single line containing the string `s`.

### Output Format
`true` or `false`

### Example 1
```
Input:
A man, a plan, a canal: Panama

Output:
true
```

### Constraints
- `1 <= |s| <= 2 * 10^5`
"""

A_PLUS_B_MD = """# A + B

The classic introductory problem.

Given two integers `A` and `B`, print their sum.

### Input Format
```
A B
```

### Output Format
```
A + B
```

### Example 1
```
Input:
1 2

Output:
3
```

### Constraints
- `-10^9 <= A, B <= 10^9`
"""

MAX_SUBARRAY_MD = """# Maximum Subarray

Given an integer array `nums`, find the contiguous subarray (containing at least one number) which has the largest sum, and print that sum.

### Input Format
```
n
a1 a2 ... an
```

### Output Format
```
max_sum
```

### Example 1
```
Input:
9
-2 1 -3 4 -1 2 1 -5 4

Output:
6
```
Explanation: `[4, -1, 2, 1]` has the largest sum `6`.

### Constraints
- `1 <= n <= 10^5`
- `-10^4 <= ai <= 10^4`
"""

BINARY_SEARCH_MD = """# Binary Search

Given a sorted array of distinct integers `nums` and a target value `target`, return the index if the target is found. If not, return `-1`.

### Input Format
```
n
a1 a2 ... an
target
```

### Output Format
```
index
```

### Example 1
```
Input:
6
-1 0 3 5 9 12
9

Output:
4
```

### Example 2
```
Input:
6
-1 0 3 5 9 12
2

Output:
-1
```

### Constraints
- `1 <= n <= 10^4`
- `-10^4 <= ai, target <= 10^4`
- `nums` is sorted in ascending order with distinct values
"""


PROBLEMS = [
    {
        "title": "Two Sum",
        "slug": "two_sum",
        "difficulty": "Easy",
        "tags": ["Array", "Hash Table"],
        "statement": TWO_SUM_MD,
        "time_limit_ms": 2000,
        "memory_limit_mb": 256,
        "test_cases": [
            {"input": "4\n2 7 11 15\n9\n", "expected": "0 1\n", "sample": True},
            {"input": "3\n3 2 4\n6\n", "expected": "1 2\n", "sample": True},
            {"input": "2\n3 3\n6\n", "expected": "0 1\n", "sample": False},
            {"input": "5\n1 5 3 7 9\n12\n", "expected": "1 3\n", "sample": False},
        ],
    },
    {
        "title": "Valid Palindrome",
        "slug": "valid_palindrome",
        "difficulty": "Easy",
        "tags": ["String", "Two Pointers"],
        "statement": VALID_PALINDROME_MD,
        "time_limit_ms": 1000,
        "memory_limit_mb": 256,
        "test_cases": [
            {"input": "A man, a plan, a canal: Panama\n", "expected": "true\n", "sample": True},
            {"input": "race a car\n", "expected": "false\n", "sample": True},
            {"input": " \n", "expected": "true\n", "sample": False},
            {"input": "0P\n", "expected": "false\n", "sample": False},
        ],
    },
    {
        "title": "A + B",
        "slug": "a_plus_b",
        "difficulty": "Easy",
        "tags": ["Math", "Implementation"],
        "statement": A_PLUS_B_MD,
        "time_limit_ms": 1000,
        "memory_limit_mb": 256,
        "test_cases": [
            {"input": "1 2\n", "expected": "3\n", "sample": True},
            {"input": "0 0\n", "expected": "0\n", "sample": True},
            {"input": "-5 10\n", "expected": "5\n", "sample": False},
            {"input": "1000000000 1000000000\n", "expected": "2000000000\n", "sample": False},
            {"input": "-7 -3\n", "expected": "-10\n", "sample": False},
        ],
    },
    {
        "title": "Maximum Subarray",
        "slug": "maximum_subarray",
        "difficulty": "Medium",
        "tags": ["Array", "Dynamic Programming", "Divide and Conquer"],
        "statement": MAX_SUBARRAY_MD,
        "time_limit_ms": 2000,
        "memory_limit_mb": 256,
        "test_cases": [
            {"input": "9\n-2 1 -3 4 -1 2 1 -5 4\n", "expected": "6\n", "sample": True},
            {"input": "1\n1\n", "expected": "1\n", "sample": True},
            {"input": "5\n-1 -2 -3 -4 -5\n", "expected": "-1\n", "sample": False},
            {"input": "4\n5 4 -1 7\n", "expected": "15\n", "sample": False},
            {"input": "3\n-2 0 -1\n", "expected": "0\n", "sample": False},
        ],
    },
    {
        "title": "Binary Search",
        "slug": "binary_search",
        "difficulty": "Easy",
        "tags": ["Array", "Binary Search"],
        "statement": BINARY_SEARCH_MD,
        "time_limit_ms": 1000,
        "memory_limit_mb": 256,
        "test_cases": [
            {"input": "6\n-1 0 3 5 9 12\n9\n", "expected": "4\n", "sample": True},
            {"input": "6\n-1 0 3 5 9 12\n2\n", "expected": "-1\n", "sample": True},
            {"input": "1\n5\n5\n", "expected": "0\n", "sample": False},
            {"input": "5\n1 2 3 4 5\n1\n", "expected": "0\n", "sample": False},
            {"input": "5\n1 2 3 4 5\n5\n", "expected": "4\n", "sample": False},
        ],
    },
]


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        admin_user = User(
            username="admin",
            email="admin@yukticode.com",
            hashed_password=get_password_hash("password"),
            is_admin=True,
        )
        db.add(admin_user)
        await db.commit()
        await db.refresh(admin_user)

        for spec in PROBLEMS:
            problem = Problem(
                title=spec["title"],
                author_id=admin_user.id,
                is_published=True,
                difficulty=spec["difficulty"],
                tags=json.dumps(spec["tags"]),
                statement=spec["statement"],
                time_limit_ms=spec["time_limit_ms"],
                memory_limit_mb=spec["memory_limit_mb"],
            )
            db.add(problem)
            await db.commit()
            await db.refresh(problem)

            cases = [
                TestCase(
                    problem_id=problem.id,
                    input_data=tc["input"],
                    expected_output=tc["expected"],
                    is_sample=tc["sample"],
                    score=10,
                )
                for tc in spec["test_cases"]
            ]
            db.add_all(cases)
            await db.commit()

            print(
                f"  + {spec['title']} "
                f"({len(spec['test_cases'])} tests)"
            )

        print(f"\nSeeded admin user + {len(PROBLEMS)} problems into DB.")


if __name__ == "__main__":
    asyncio.run(seed())
