from app import create_app
from app.config import settings
import uvicorn

app = create_app()
def main():
    host = settings.HOST
    port = settings.PORT
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()

