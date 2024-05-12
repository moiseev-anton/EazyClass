from django.contrib import admin
from .models import *

admin.site.register(User)
admin.site.register(Faculty)
admin.site.register(Group)
admin.site.register(Teacher)
admin.site.register(Subject)
admin.site.register(Lesson)
admin.site.register(Classroom)

