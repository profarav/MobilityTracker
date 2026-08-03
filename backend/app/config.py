from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://mobility:mobility@db:5432/mobility_tracker"

    model_config = {"env_file": ".env"}


settings = Settings()
