from rest_framework import generics, viewsets
from scheduler.models import Group
from .serializers import GroupSerializer


# class GroupAPIView(generics.RetrieveAPIView):
#     queryset = Group.objects.all()
#     serializer_class = GroupSerializer

class GroupViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
