import praw
import json
import yaml
import os
import re
from collections import deque
import time

#Globals

r=praw.Reddit(user_agent='reddit cyborg by /u/captainmeta4',
              client_id='MSr7KePev8-f4g',
              client_secret=os.environ.get('client_secret'),
              username='captainmeta4',
              password=os.environ.get('password'))

SUBREDDIT = r.subreddit('cyborg_noeatnosleep')
ME = r.redditor('captainmeta4')

DISCLAIMER = "\n\n*^(I am a cyborg, and this action was performed automatically. Please message the moderators with any concerns.)"
LOGGING_ENABLED = False



def xor(bool1, bool2):

    b1 = bool(bool1)
    b2 = bool(bool2)

    if (b1 or b2) and not (b1 and b2):
        return True
    else:
        return False

class Rule():

    #Rule object which stores rule data

    def __init__(self, data={}):

        self.data=data

        _valid_fields = [
            'type',
            'subreddit',
            'author_name',
            'body',
            'body_regex',
            'domain',
            'action',
            'reason',
            'comment',
            'ban_message',
            'ban_duration',
            'invert',
            'message_subject',
            'message',
            'title'
            ]

        for entry in data:
            if entry not in _valid_fields:
                raise KeyError("unknown field `%s` in rule" % entry)

        #set values with defaults 
        self.subreddit      = data.get('subreddit', [])
        self.type           = data.get('type', "both")
        self.author_name    = data.get('author_name', [])
        self.body           = data.get('body', [])
        self.body_regex     = data.get('body_regex', [])
        self.domain         = data.get('domain', [])
        self.title          = data.get('title',[])

        self.action         = data.get('action', [])
        self.reason         = data.get('reason', "")
        self.comment        = data.get('comment', "")
        self.ban_message    = data.get('ban_message', "")
        self.ban_duration   = data.get('ban_duration', None)
        self.message_subject= data.get('message_subject',"Automatic Notification")
        self.message        = data.get('message',"")

        self.invert = data.get('invert', [])


                
    def __str__(self):
        return yaml.dump(self.data)

    def match_thing(self, thing):

        #returns False if it's not a match,
        #True if successful match

        #begin checking
        if self.type=="both":
            pass
        elif isinstance(thing, praw.objects.Comment):
            if "submission" in self.type:
                print('type mismatch - thing is not submission')
                return False
            
        elif isinstance(thing, praw.objects.Submission):
            if self.type == "comment":
                print('type mismatch - thing is not comment')
                return False
            elif self.type == "link submission" and thing.url == thing.permalink:
                print('type mismatch - thing is not link submission')
                return False
            elif self.type == "text submission" and thing.url != thing.permalink:
                print('type mismatch - thing is not text submission')
                return False

        if self.subreddit:
            if xor(not any(x.lower()==thing.subreddit.display_name.lower() for x in self.subreddit), "subreddit" in self.invert):
                print('subreddit mismatch')
                return False

        if self.author_name:
            if getattr(thing, 'author', None):
                if xor(not any(x.lower()==thing.author.name.lower() for x in self.author_name), "author_name" in self.invert):
                    print('author mismatch')
                    return False

        if self.title:
            title = getattr(thing, 'title', None)

            if not title:
                print('thing does not have title')
                return False

            if xor(not any(x in title for x in self.title), "title" in self.invert):
                print('title mismatch')
                return False

        if self.domain:
            if not getattr(thing, 'domain', None):
                print('domain failed')
                return False

            if xor(not any(thing.domain.endswith(x) for x in self.domain), "domain" in self.invert):
                print('domain mismatch')
                return False

        if self.body:

            #get body text from comment or selftext
            body = getattr(thing, 'body', getattr(thing, 'selftext', None))
            if not body:
                print('thing does not have body')
                return False
            
            if xor(not any(x in body for x in self.body), "body" in self.invert):
                print('body mismatch')
                return False

        if self.body_regex:

            body = getattr(thing, 'body', getattr(thing, 'selftext', None))

            if not body:
                print('thing does not have body for body_regex')
                return False

            if xor(not any(re.search(x.lower(), body.lower()) for x in self.body_regex), "body_regex" in self.invert):
                print('body regex mismatch')
                return False

            


        #at this point all criteria are satisfied. Act.
        print("rule triggered at "+thing.permalink)

        return True

    def act_on(self, thing):

        #see if we need to fetch the parent thing
        #if we do but it's not a comment then return
        if any("parent" in x for x in self.action):
            if isinstance(thing, praw.objects.Comment):
                parent=r.get_info(thing_id=thing.parent_id)
            else:
                return False
            

        #do all actions

        if "remove" in self.action:
            thing.remove()

        if "remove_parent" in self.action:
            parent.remove()

        if "spam" in self.action:
            thing.remove(spam=True)

        if "spam_parent" in self.action:
            parent.remove(spam=True)

        if "ban" in self.action:
            thing.subreddit.add_ban(thing.author, note=self.reason, ban_message=self.ban_message, duration = self.ban_duration)

        if "ban_parent" in self.action:
            thing.subreddit.add_ban(parent.author, note=self.reason, ban_message=self.ban_message, duration = self.ban_duration)

        if "report" in self.action:
            thing.report(reason=self.reason)

        if "report_parent" in self.action:
            parent.report(reason=self.reason)

        if "approve" in self.action:
            thing.approve()

        if "approve_parent" in self.action:
            parent.approve()

        if "rts" in self.action:
            r.submit("spam", "Overview for /u/"+thing.author.name, url="http://reddit.com/user/"+thing.author.name)

        if "rts_parent" in self.action:
            r.submit("spam", "Overview for /u/"+parent.author.name, url="http://reddit.com/user/"+parent.author.name)

        if self.comment:
            comment.reply(self.comment).distinguish()

        if self.message:
            r.send_message(comment.author, self.message_subject, self.message)

        return True
        

class Bot():

    def __init__(self):

        self.start_time = time.time()

        self.rules=[]

        self.already_done = deque([],maxlen=400)

    def run(self):

        #self.login()
        self.load_rules()
        self.mainloop()

    def login(self):

        r.login('captainmeta','1kCMamfrdt', disable_warning=True)

    def load_rules(self):

        #get wiki page

        print('loading rules...')
        wiki_page = praw.models.WikiPage(r,SUBREDDIT, "users/noeatnosleep").content_md
        try:
            i=1
            for entry in yaml.safe_load_all(wiki_page):
                self.rules.append(Rule(data=entry))
                i+=1
        except KeyError as e:
            #r.send_message(ME, 'Error in Rule #'+str(i),e).mark_as_unread()
            print('Error in Rule #'+str(i),e)
        except:
            #r.send_message(ME, "Unable to parse rules at Rule#"+str(i), "Unable to parse")
            print('Unable to parse in Rule #'+str(i))
        print('...done')

    def reload_rules(self):
        print('Rules reload ordered')
        self.rules=[]
        self.load_rules()


    def full_stream(self):
        #unending generator which returns content from /new, /comments, and /edited of /r/mod

        subreddit = r.subreddit('mod-cyborg_noeatnosleep')

        while True:
            single_round_stream = []

            #fetch /new
            for submission in subreddit.get_new(limit=100):

                #avoid old work (important for bot startup)
                if submission.created_utc < self.start_time:
                    continue

                #avoid duplicate work
                if submission.fullname in self.already_done:
                    continue
                
                self.already_done.append(submission.fullname)
                single_round_stream.append(submission)

            #fetch /comments
            for comment in subreddit.get_comments(limit=100):

                #avoid old work
                if comment.created_utc < self.start_time:
                    continue

                #avoid duplicate work
                if comment.fullname in self.already_done:
                    continue
                self.already_done.append(comment.fullname)
                single_round_stream.append(comment)

            #fetch /edited
            for thing in subreddit.get_edited(limit=100):
                #ignore removed things
                if thing.banned_by:
                    continue

                if thing.edited < self.start_time:
                    continue
                
                #uses duples so that new edits are detected but old edits are passed by
                #.edited is the edit timestamp (False on unedited things)
                if (thing.fullname, thing.edited) in self.already_done:
                    continue
                
                self.already_done.append((thing.fullname, thing.edited))
                single_round_stream.append(thing)

            for thing in single_round_stream:

                yield thing

    def log_action(self, rule, thing):

        rule_text = str(rule)
        rule_text = '    '+rule_text.replace('\n','\n    ')

        text = thing.permalink + '\n\n' + rule_text

        title = "Activated on thing %(fullname)s by /u/%(user)s in /r/%(sub)s" % {'fullname':thing.fullname, 'user':thing.author.name, 'sub': thing.subreddit.display_name}

        r.submit(SUBREDDIT, title, text=text)

    def mainloop(self):

        for thing in self.full_stream():
            print('checking thing '+thing.fullname+' by /u/'+thing.author.name+' in /r/'+thing.subreddit.display_name)

            #hard code rule reload
            if isinstance(thing, praw.objects.Comment):
                if thing.author==ME and thing.body=="!reload":
                    thing.delete()
                    self.reload_rules()
                    continue
            
            for rule in self.rules:
                if rule.match_thing(thing):
                    if rule.act_on(thing):
                        if LOGGING_ENABLED:
                            self.log_action(rule, thing)
                    


if __name__=="__main__":
    b=Bot()
    b.run()
