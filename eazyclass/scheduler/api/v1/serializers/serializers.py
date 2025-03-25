from rest_framework import serializers

from scheduler.models import Group, Faculty, User, SocialAccount

SOCIAL_ID_MAX_LENGTH = SocialAccount._meta.get_field('social_id').max_length
PROVIDER_MAX_LENGTH = SocialAccount._meta.get_field('provider').max_length
FIRST_NAME_MAX_LENGTH = User._meta.get_field('first_name').max_length
LAST_NAME_MAX_LENGTH = User._meta.get_field('last_name').max_length


class FacultieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Faculty
        fields = ['id', 'title', 'short_title']


class GroupSerializer(serializers.ModelSerializer):
    faculty = FacultieSerializer()

    class Meta:
        model = Group
        fields = ['id', 'title', 'grade', 'faculty']


class NonceSerializer(serializers.Serializer):
    nonce = serializers.UUIDField(required=True)


class BotAuthSerializer(serializers.Serializer):
    social_id = serializers.CharField(max_length=SOCIAL_ID_MAX_LENGTH, required=True)
    provider = serializers.ChoiceField(choices=SocialAccount.PLATFORM_CHOICES)
    first_name = serializers.CharField(max_length=FIRST_NAME_MAX_LENGTH, required=False, allow_blank=True,
                                       allow_null=True)
    last_name = serializers.CharField(max_length=LAST_NAME_MAX_LENGTH, required=False, allow_blank=True,
                                      allow_null=True)
    extra_data = serializers.JSONField(required=False, allow_null=True)
    nonce = serializers.UUIDField(required=False)

    def create(self, validated_data):
        social_id = validated_data['social_id']
        provider = validated_data['provider']
        first_name = validated_data['first_name']
        last_name = validated_data['last_name']
        extra_data = validated_data.get('extra_data', {})

        user, created = User.objects.get_or_create_user(
            social_id=social_id,
            provider=provider,
            first_name=first_name,
            last_name=last_name,
            extra_data=extra_data
        )

        return user, created

    def save(self, **kwargs):
        return self.create(self.validated_data)
