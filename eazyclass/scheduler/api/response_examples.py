from drf_spectacular.utils import OpenApiResponse, OpenApiExample

from scheduler.api.v1.serializers import SubscriptionSerializer

group_example = {
                    "type": "subscription",
                    "id": "1",
                    "attributes": {
                        "object": {
                            "type": "group",
                            "id": "4",
                            "attributes": {
                                "title": "4-GROUP-42",
                                "grade": "4",
                                "link": "view.php?id=00042"
                            }
                        }
                    }
                }

teacher_example = {
                    "type": "subscription",
                    "id": "17",
                    "attributes": {
                        "object": {
                            "type": "teacher",
                            "id": "5",
                            "attributes": {
                                "full_name": "Иванов Иван Иванович",
                                "short_name": "Иванов И.И."
                            }
                        }
                    }
                }


SubscriptionSuccessResponse = OpenApiResponse(
    response=SubscriptionSerializer,
    description="Successful subscription response",
    examples=[
        OpenApiExample(
            "Group Subscription",
            value={"data": group_example}
        ),
        OpenApiExample(
            "Teacher Subscription",
            value={"data": teacher_example}
        )
    ]
)
