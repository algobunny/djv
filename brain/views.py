import atexit
import concurrent
import json
import urllib

from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.reverse import reverse

from models import FbUser
from models import Media
from models import Status
from serializers import FbUserSerializer
from serializers import MediaSerializer
from serializers import StatusSerializer
from tasks import initialise_fb_user

from djv.utils import get_api_secrets

from KalturaImages import GetKS
from KalturaUpload import get_upload_token
from ThinkThread import think


#EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4)
#def shutdown():
#    EXECUTOR.shutdown(wait=True)
#atexit.register(shutdown)


class StatusList(APIView):
    """
    List all status progress for media tagging.
    """

    def get(self, request, format=None):
        statuses = Status.objects.all()
        serializer = StatusSerializer(statuses, many=True)
        return Response(serializer.data)

class StatusDetail(APIView):
    """
    Get status progress for a particular entry.
    """

    def get(self, request, entry_id, format=None):
        query = Status.objects.filter(media_id=entry_id)
        if query.count():
            serializer = StatusSerializer(query.all(), many=True)
            return Response(serializer.data)

        return Response(status=status.HTTP_404_NOT_FOUND)

class MediaList(APIView):
    """
    List all media, or upload a new media.
    """

    def get(self, request, format=None):
        medias = Media.objects.all()
        serializer = MediaSerializer(medias, many=True)
        return Response(serializer.data)

    @csrf_exempt
    def post(self, request, format=None):
        # TODO: begin process of accessing external APIs and tagging
        # currently only creates a dummy media object

        entry_id = request.DATA.get('id')
        services = request.DATA.get('services', {})

        query = Media.objects.filter(id=entry_id)
        media = None
        if query.count():
            media = query.get()

        serializer = MediaSerializer(media, data={'id': entry_id})
        if serializer.is_valid():
            serializer.save()

            from brain.tasks import think
            domain_uri = 'http://%s' % request.get_host()
            think(entry_id, services, domain_uri)
            #think(entry_id, services)

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FbProfileDetail(APIView):
    """
    Retrieve Facebook user details and initialise facial recognition services.
    """

    def get(self, request, format=None):
        args = urllib.urlencode(dict(access_token=request.GET.get('access_token', '')))
        profile = json.load(urllib.urlopen('https://graph.facebook.com/me?%(args)s' % locals()))

        serializer = FbUserSerializer()
        if 'id' in profile:
            fb_user = FbUser(id=profile['id'],
                            name=profile['name'],
                            is_initialised=False)
            serializer = FbUserSerializer(fb_user)

        return Response(serializer.data)

    def post(self, request, format=None):
        access_token = str(request.DATA.get('access_token', ''))
        force_initialise = bool(request.DATA.get('force_initialise', False))

        args = urllib.urlencode(dict(access_token=access_token))
        url = 'https://graph.facebook.com/me?%(args)s' % locals()
        profile = json.load(urllib.urlopen(url))
        fb_user, created = FbUser.objects.get_or_create(id=profile['id'])
        if force_initialise or created or not fb_user.is_initialised:
            initialise_fb_user('http://%s' % request.get_host(), access_token)
            fb_user.is_initialised = True
            fb_user.name = profile['name']
            fb_user.save()

        return Response(FbUserSerializer(fb_user).data, status=status.HTTP_201_CREATED)


class FbFriendList(APIView):
    """
    List all Facebook current user friends.
    """

    def get(self, request, format=None):
        access_token = request.GET.get('access_token', '')
        friends = json.load(urllib.urlopen('https://graph.facebook.com/me/friends?%s' % urllib.urlencode(dict(access_token=access_token))))

        serializer = FbUserSerializer([], many=True)
        return Response(serializer.data)

@api_view(('GET',))
def api_root(request, format=None):
    return Response({
        'medias': reverse('media-list', request=request, format=format),
        'status': reverse('status-list', request=request, format=format),
        'status_detail': reverse('status-detail', request=request, format=format,),
        'fb_friends': reverse('fb-friends-list', request=request, format=format),
        'fb_profile_detail': reverse('fb-profile-detail', request=request, format=format),
    })

def webview(request):
    return render(request, 'brain/webview.html')
 
@csrf_exempt
def upload(request):
    secrets = get_api_secrets()['kaltura']
    ks = GetKS()
    upload_token = get_upload_token(ks)
    content = {'ks':ks, 'partnerId': secrets['partner_id'], 'uploadToken':upload_token }
    return render(request, 'brain/upload.html', content)
  
def list(request):
    secrets = get_api_secrets()['kaltura']
    ks = GetKS()
    upload_token = get_upload_token(ks)
    content = {'ks':ks, 'partnerId': secrets['partner_id'], 'uploadToken':upload_token }
    return render(request, 'brain/list.html', content)
