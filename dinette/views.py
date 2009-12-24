from django.http import HttpResponse, Http404
from django.shortcuts import render_to_response, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.template import Context , loader
from django.template import RequestContext
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.contrib.syndication.feeds import Feed
from django.contrib.auth.models import User , Group
from django.conf import settings
from django.views.generic.list_detail import object_list

from  datetime  import datetime
import logging
import simplejson

from dinette.models import Ftopics , SuperCategory ,Category ,Reply, DinetteUserProfile
from dinette.forms import  FtopicForm , ReplyForm



#Create module logger
#several logging configurations are configured in the models
mlogger = logging.getLogger(__name__)


json_mimetype = 'application/javascript'
def index_page(request):
    mlogger.info("In the index page")
    forums = SuperCategory.objects.all()
    accesslist = ""
    jumpflag = False
    
    
    #groups which this user has access
    if request.user.is_authenticated() :
            
            groups = [group for group in request.user.groups.all()] + [group for group in Group.objects.filter(name="general")]
    else:
            #we are treating user who have not loggedin belongs to general group
            groups = Group.objects.filter(name="general")
        
    
    #logic which decide which forum does this user have access to
    for forum in forums :
        
        jumpflag = False
        for group in groups :           
            for gforum in group.can_access_forums.all() :
                
                if gforum.id == forum.id :
                    #the respective user can access the forum
                    #accesslist.append(True)
                    accesslist = "1"+accesslist
                    mlogger.debug("appending true ...... "+str(forum.id))
                    jumpflag = True
                    break
        
          #already one group has acces to forum no need to check whether other groups have access to it or not        
            if jumpflag:
                mlogger.debug("breaking up"+str(jumpflag)) 
                break
        
        if jumpflag == False:
            mlogger.debug("appending false.........."+str(forum.id))
            accesslist = "0"+accesslist
            
   
    mlogger.debug("what is the accesslist "+accesslist)
    totaltopics = Ftopics.objects.count()
    totalposts = totaltopics + Reply.objects.count()
    totalusers =  User.objects.count()
    import datetime
    now = datetime.datetime.now()
    users_online = DinetteUserProfile.objects.filter(last_activity__gte =  now - datetime.timedelta(seconds = 900)).count()
    last_registered_user = User.objects.order_by('-date_joined')[0]
    try:
        user_access_list = int(accesslist)
    except ValueError:
        user_access_list = 0
    payload = {'users_online':users_online, 'forums_list':forums,'totaltopics':totaltopics,
               'totalposts':totalposts,'totalusers':totalusers,'user_access_list':user_access_list,
               'last_registered_user':last_registered_user}
    return render_to_response("dinette/mainindex.html", payload,RequestContext(request))



def category_details(request, categoryslug,  pageno=1) :
    mlogger.info("In the welcome page.......................")
    mlogger.debug("Type of request.user %s" % type(request)  )   
    #buid a form for posting topics
    topicform = FtopicForm()
    category = Category.objects.get(slug=categoryslug)
    queryset = Ftopics.objects.filter(category__id__exact = category.id)    
    paginator = Paginator(queryset,settings.TOPIC_PAGE_SIZE)
    topiclist = paginator.page(pageno)
    return render_to_response("dinette/home.html", {'topicform': topicform,'category':category,'authenticated':request.user.is_authenticated(),'topic_list':topiclist},RequestContext(request))
    
    
       
def topic_list(request):
    queryset = Ftopics.objects.all()                
    return object_list(request, queryset = queryset, template_name = 'dinette/topiclist.html', template_object_name='topic', paginate_by=2)
    
def topic_detail(request, categoryslug, topic_slug , pageno = 1):
    topic = get_object_or_404(Ftopics, slug = topic_slug)
    show_moderation_items = False
    if request.user in topic.category.moderated_by.all():
        show_moderation_items = True
    #some body has viewed this topic
    topic.viewcount = topic.viewcount + 1
    topic.save()
    #we also need to display the reply form
    paginator = Paginator(topic.reply_set.all(),settings.REPLY_PAGE_SIZE)
    replylist = paginator.page(pageno)
    replyform = ReplyForm()
    payload = {'topic': topic, 'replyform':replyform,'reply_list':replylist, 'show_moderation_items':show_moderation_items}
    return render_to_response("dinette/topic_detail.html", payload, RequestContext(request))

@login_required
def postTopic(request) :
    mlogger.info("In post Topic page.....................")
    mlogger.debug("Type of request.user %s" % type(request.user)  )
    
    topic = FtopicForm(request.POST,request.FILES)
   
    if topic.is_valid() == False :
        d = {"is_valid":"false","response_html":topic.as_table()}
        json = simplejson.dumps(d)
        if request.FILES :
            json = "<textarea>"+simplejson.dumps(d)+"</textarea>"
        else:
            json = simplejson.dumps(d)
        return HttpResponse(json, mimetype = json_mimetype)                    
     
     
    #code which checks for flood control
    if (datetime.now() -(request.user.get_profile().last_posttime)).seconds <= settings.FLOOD_TIME :
    #oh....... user trying to flood us Stop him
        d2 = {"is_valid":"flood","errormessage":"Flood control.................."}
        if request.FILES : 
            json = "<textarea>"+simplejson.dumps(d2)+"</textarea>"
        else :
            json = simplejson.dumps(d2)  
        return HttpResponse(json, mimetype = json_mimetype)
         
    ftopic = topic.save(commit=False)     
    #only if there is any file
    if request.FILES :
        if(request.FILES['file'].content_type.find("image") >= 0 ) :
            ftopic.attachment_type = "image"
        else :
            ftopic.attachment_type = "text"
        ftopic.filename = request.FILES['file'].name
        
    ftopic.posted_by = request.user
    mlogger.debug("categoryid= %s" %request.POST['categoryid'])
    ftopic.category  = Category.objects.get(pk = request.POST['categoryid'])
    #Assigning user rank
    mlogger.debug("Assigning an user rank and last posted datetime")     
    assignUserElements(request.user)
    ftopic.save()
    mlogger.debug("what is the message (%s %s) " % (ftopic.message,ftopic.subject))    
    payload = {'topic':ftopic}
    response_html = render_to_string('dinette/topic_detail_frag.html', payload,RequestContext(request))
    mlogger.debug("what is the response = %s " % response_html)
  
    d2 = {"is_valid":"true","response_html":response_html}
    #this the required for ajax file uploads
    if request.FILES : 
        json = "<textarea>"+simplejson.dumps(d2)+"</textarea>"
    else :
        json = simplejson.dumps(d2) 
    return HttpResponse(json, mimetype = json_mimetype)
    
@login_required    
def postReply(request) :
    mlogger.info("in post reply.................")
    freply = ReplyForm(request.POST,request.FILES)
    
    if freply.is_valid() == False :
        d = {"is_valid":"false","response_html":freply.as_table()}
        json = simplejson.dumps(d)
        if request.FILES :
            json = "<textarea>"+simplejson.dumps(d)+"</textarea>"
        else:
            json = simplejson.dumps(d)
        return HttpResponse(json, mimetype = json_mimetype)
        
        
        
    #code which checks for flood control
    if (datetime.now() -(request.user.get_profile().last_posttime)).seconds <= settings.FLOOD_TIME:
    #oh....... user trying to flood us Stop him
         d2 = {"is_valid":"flood","errormessage":"You have posted message too recently. Please wait a while before trying again."}
         if request.FILES : 
               json = "<textarea>"+simplejson.dumps(d2)+"</textarea>"
         else :
               json = simplejson.dumps(d2)  
         return HttpResponse(json, mimetype = json_mimetype)        
        
    
    reply = freply.save(commit=False)    
     #only if there is any file
    if len(request.FILES.keys()) == 1 :
        if(request.FILES['file'].content_type.find("image") >= 0 ) :
            reply.attachment_type = "image"
        else :
            reply.attachment_type = "text"
            
        reply.filename = request.FILES['file'].name
        
    reply.posted_by = request.user
    mlogger.debug("toipcid= %s" %request.POST['topicid'])
    reply.topic = Ftopics.objects.get(pk = request.POST['topicid'])
    #Assigning user rank
    mlogger.debug("Assigning an user rank, and last posted datetime")
    assignUserElements(request.user) 
    reply.save()
    payload = {'reply':reply}    
    mlogger.debug("what is the replymesage = %s" %reply.message)
    response_html = render_to_string('dinette/replydetail_frag.html', payload ,RequestContext(request))
    mlogger.debug("what is the response = %s " % response_html)
    
    d2 = {"is_valid":"true","response_html":response_html}
        
    if request.FILES :
        #this the required for ajax file uploads
        json = "<textarea>"+simplejson.dumps(d2)+"</textarea>"
    else:
        json = simplejson.dumps(d2)
    
    return HttpResponse(json, mimetype = json_mimetype)  
    
    
    
class LatestTopicsByCategory(Feed):
     title_template = 'dinette/feeds/title.html'
     description_template = 'dinette/feeds/description.html'

     def get_object(self, whichcategory):
         mlogger.debug("Feed for category %s " % whichcategory)
         return get_object_or_404(Category, slug=whichcategory[0])
         
     def title(self, obj):
        return "Latest topics in category %s" % obj.name
     
     def link(self, obj):
        return  settings.SITE_URL

     def items(self, obj):
        return obj.ftopics_set.all()[:10]
       
     #construct these links by means of reverse lookup  by
     #using permalink decorator
     def item_link(self,obj):
        return  obj.get_absolute_url()
     
     def item_pubdate(self,obj):
        return obj.created_on
    
    
class LatestRepliesOfTopic(Feed):
     title_template = 'dinette/feeds/title.html'
     description_template = 'dinette/feeds/description.html'

     def get_object(self, whichtopic):
         mlogger.debug("Feed for category %s " % whichtopic)
         return get_object_or_404(Ftopics, slug=whichtopic[0])
         
     def title(self, obj):
        return "Latest replies in topic %s" % obj.subject
     
     def link(self, obj):
        return  settings.SITE_URL

     def items(self, obj):
        list = []
        list.insert(0,obj)
        for obj in obj.reply_set.all()[:10] :
            list.append(obj)           
        return list
       
     #construct these links by means of reverse lookup  by
     #using permalink decorator
     def item_link(self,obj):       
        return  obj.get_absolute_url()
     
     def item_pubdate(self,obj):
        return obj.created_on
    
    
    
def assignUserElements(user):
    ranks = getattr(settings, 'RANKS_NAMES_DATA')
    rank = ''
    if ranks:
        totalposts = user.ftopics_set.count() + user.reply_set.count()
        for el in ranks:
            if totalposts == el[0]:
                rank = el[1]
        if rank:    
            userprofile = user.get_profile()
            userprofile.userrank = rank
            #this is the time when user posted his last post
            userprofile.last_posttime = datetime.now()
            userprofile.save()
    
    
###Moderation views###
@login_required
def moderate_topic(request, topic_id, action):
    topic = get_object_or_404(Ftopics, pk = topic_id)
    if not request.user in topic.category.moderated_by.all():
        raise Http404
    if request.method == 'POST':
        if action == 'close':
            if topic.is_closed:
                message = 'You have reopened topic %s'%topic.subject
            else:
                message = 'You have closed topic %s'%topic.subject
            topic.is_closed = not topic.is_closed
        elif action == 'announce':
            if topic.announcement_flag:
                message = '%s is no longer an announcement.' % topic.subject
            else:
                message = '%s is now an announcement.' % topic.subject
            topic.announcement_flag = not topic.announcement_flag
        elif action == 'sticky':
            if topic.is_sticky:
                message = '%s has been unstickied.' % topic.subject
            else:
                message = '%s has been stickied.' % topic.subject
            topic.is_sticky = not topic.is_sticky
        elif action == 'hide':
            topic.is_hidden = True
            message = '%s has been hidden and wont show up any further.' % topic.subject
        topic.save()
        payload = {'topic_id':topic.pk, 'message':message}
        resp = simplejson.dumps(payload)
        return HttpResponse(resp, mimetype = json_mimetype)
    else:
        return HttpResponse('This view must be called via post')
    
def login(request):
    if getattr(settings, 'DINETTE_LOGIN_TEMPLATE', None):
        return render_to_response(settings.DINETTE_LOGIN_TEMPLATE, {}, RequestContext(request, {'fb_api_key':settings.FACEBOOK_API_KEY,}))
    else:
        from django.contrib.auth.views import login
        return login(request)
        
        
    
    