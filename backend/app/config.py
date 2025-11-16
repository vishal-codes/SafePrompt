from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BASE_MODEL: str = Field(default="meta-llama/Llama-3.2-3B-Instruct")
    ADAPTER_REPO: str = Field(default="chinu-codes/llama-3.2-3b-pii-redactor-lora")

    SEQ_LEN: int = Field(default=512)
    MAX_NEW_TOKENS: int = Field(default=96)
    DO_SAMPLE: bool = Field(default=False)

    NUM_THREADS: int = Field(default=4)
    LOG_LEVEL: str = Field(default="INFO")

    HF_TOKEN: str | None = None          
    HF_LOCAL_ONLY: bool = Field(default=False)

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
