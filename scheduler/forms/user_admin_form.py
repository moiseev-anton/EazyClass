from django.contrib.auth.forms import AdminUserCreationForm


class UserCreationForm(AdminUserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].required = False
        self.fields["username"].help_text = (
            "Можно оставить пустым — будет сгенерировано автоматически (sXXXXXX)"
        )

    def save(self, commit=True):
        user = super().save(commit=False)

        if not user.username:  # если не ввели username → генерируем
            user.username = user.__class__.objects.generate_default_username()

        if commit:
            user.save()
            self.save_m2m()

        return user
