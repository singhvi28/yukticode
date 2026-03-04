# YuktiCode Online Judge

The YuktiCode Online Judge is a full-stack platform for competitive programming. It features a React frontend and a REST API built using FastAPI for executing user code asynchronously.

The server takes user-submitted code along with required parameters and assigns the execution tasks to workers via RabbitMQ. Upon completion, the workers make a POST request to callback URL provided in the request to return the status of the executed task.

This Judge Server is a wrapper REST api for the [Judger System](https://github.com/AbhishekBhosale46/onlineJudge-Judger/).

## Features

- **Full-Featured Frontend**: React/Vite SPA with Monaco Editor integration and a premium dark theme.
- **Asynchronous Execution**: Uses RabbitMQ to assign tasks to independent workers.
- **Multi-Language Support**: Safe execution environments for Python, C++, Java, and more.
- **Horizontal Scalability**: Add more worker instances easily to handle increased loads.

## Technologies Used

### Frontend
![React](https://img.shields.io/badge/react-%2320232a.svg?style=for-the-badge&logo=react&logoColor=%2361DAFB)
![Vite](https://img.shields.io/badge/vite-%23646CFF.svg?style=for-the-badge&logo=vite&logoColor=white)

### Backend
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/postgresql-4169e1?style=for-the-badge&logo=postgresql&logoColor=white)
![RabbitMQ](https://img.shields.io/badge/Rabbitmq-FF6600?style=for-the-badge&logo=rabbitmq&logoColor=white)

![Judge Server System Diagram](https://github.com/AbhishekBhosale46/OnlineJudge-JudgeServer/assets/58450561/c365ba52-4525-4809-8240-818790b8d91e)

## Installation & Running Locally

Clone the project:

```bash
git clone https://github.com/AbhishekBhosale46/OnlineJudge-JudgeServer
cd OnlineJudge-JudgeServer
```

### 1. Backend Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install python-jose[cryptography] python-multipart
```

Start the FastAPI Server:

```bash
uvicorn server.main:app --host 127.0.0.1 --port 9000 --reload
```

Start the workers (in separate terminals, with the `venv` activated):
```bash
python worker/submit_worker.py
python worker/run_worker.py
```

### 2. Frontend Setup

In a new terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:5173`.

## Testing

The project includes a comprehensive test suite written in `pytest` with 100% mocked external dependencies (no running RabbitMQ or Docker daemon required).

To run the tests:

```bash
pip install pytest pytest-asyncio httpx
pytest
```
## Usage

### Submitting a Task

To submit a task, make a POST request to the /submit or /run endpoint.

```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/submit' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "language": "string",
  "time_limit": 0,
  "memory_limit": 0,
  "src_code": "string",
  "std_in": " ",
  "expected_out": "string",
  "callback_url": "string"
}'

```

### Receiving the Callback

The worker will execute the submitted code and send a POST request to the provided callback_url with the following JSON body:

```bash
{
  "status": "AC | WA | TLE | MLE | RE | CE",
}
```

## API Reference

#### Make submit code request

```https
  POST /submit
```

| Parameter | Type     | Description                |
| :-------- | :------- | :------------------------- |
| `language` | `string` | Language of the source code |
| `time_limit` | `int` | Time limit in seconds |
| `memory_limit` | `int` | Memory limit in mb |
| `src_code` | `string` | Code to run on the server |
| `std_in` | `string` | Standard input to the program |
| `expected_out` | `string` | Expected output of the program |
| `callback_url` | `string` | Url where POST request will be made by worker |

#### Make run code request

```https
  POST /run
```
| Parameter | Type     | Description                |
| :-------- | :------- | :------------------------- |
| `language` | `string` | Language of the source code |
| `time_limit` | `int` | Time limit in seconds |
| `memory_limit` | `int` | Memory limit in mb |
| `src_code` | `string` | Code to run on the server |
| `std_in` | `string` | Standard input to the program |
| `callback_url` | `string` | Url where POST request will be made by worker |



## Contributing

Contributions are welcome! Please fork the repository and submit a pull request for any improvements or bug fixes.

- Fork the repository.
- Create a new branch (git checkout -b feature-branch).
- Make your changes.
- Commit your changes (git commit -m 'Add some feature').
- Push to the branch (git push origin feature-branch).
- Open a pull request.

