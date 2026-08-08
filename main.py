import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.main import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
