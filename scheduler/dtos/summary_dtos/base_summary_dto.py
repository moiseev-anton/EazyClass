from pydantic import BaseModel, Field

SUMMARY_REGISTRY = {}


def register_summary(cls):
    SUMMARY_REGISTRY[cls.__name__] = cls
    return cls


class BaseSummary(BaseModel):
    type: str = Field(default_factory=lambda: "BaseSummary")

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        data["type"] = self.__class__.__name__
        return data

    @classmethod
    def deserialize(cls, data: dict):
        model_cls = SUMMARY_REGISTRY.get(data.get("type"), cls)
        return model_cls.model_validate(data)

    def to_message(self, title: str = 'Отчет') -> str:
        raise NotImplementedError()

    @property
    def parts(self) -> dict[str, object]:
        """
        Ключевые смысловые части summary.
        Не обязано быть полным отображением модели.
        """
        return {}

    def to_brief(self) -> str:
        parts = ", ".join(f"{k}={v!r}" for k, v in self.parts.items())
        return f"{self.__class__.__name__}({parts})"

    def __str__(self):
        return self.to_brief()
