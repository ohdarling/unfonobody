#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp import util

import datetime
import tweepy
import oauth2 as oauth
import urlparse
from gaesessions import get_current_session

# Twitter app settings
consumer_key = 'LgDoCc2V8ai5J4varzzQ'
consumer_secret = 's7zMuqylEUgJL7gu5kJLlZIFEeZUHu0CgspLmFeWbo'

request_token_url = 'https://twitter.com/oauth/request_token'
access_token_url = 'https://twitter.com/oauth/access_token'
authorize_url = 'https://twitter.com/oauth/authorize'

consumer = oauth.Consumer(consumer_key, consumer_secret)


# jinja settings
import jinja2
import os
jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__), 'views')))

def get_twitter_api():
    session = get_current_session()
    oauth_data = session.get('oauth_data');
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(oauth_data['oauth_token'], oauth_data['oauth_token_secret'])
    api = tweepy.API(auth)
    return api


def is_logged_in():
    session = get_current_session()
    oauth_data = session.get('oauth_data');
    return oauth_data != None
    

class MainHandler(webapp.RequestHandler):
    def showLogin(self):
        template = jinja_environment.get_template('index.html')
        self.response.out.write(template.render({}))

    def get(self):
        if is_logged_in() == False:
            self.showLogin()
            return
    
        session = get_current_session()
        oauth_data = session.get('oauth_data');

        api = get_twitter_api()
        friends_ids = api.friends_ids()
        
        cur_page = 1 if 'page' not in self.request.GET else int(self.request.GET['page'])
        
        page_ids = []
        for i in range((cur_page-1)*100, min(cur_page*100, len(friends_ids))-1):
            page_ids.append(friends_ids[i])
            
        friends = api.lookup_users(page_ids)
        friends = sorted(friends, key = lambda u:datetime.datetime(1,1,1) if hasattr(u, 'status') == False else u.status.created_at)
        
        template_values = {
            'oauth_data' : oauth_data,
            'friends_ids': page_ids,
            'friends'    : friends,
            'total_pages': len(friends_ids)/100,
            'cur_page'   : cur_page,
            'has_list'   : 'has_list' in session
        }
        
        template = jinja_environment.get_template('index.html')
        self.response.out.write(template.render(template_values))


class TwitterOAuthCallbackHandler(webapp.RequestHandler):
    def get(self):
        session = get_current_session()
        
        oauth_token = self.request.GET['oauth_token'];
        oauth_token_secret = self.request.cookies.get('oauth_token_secret');
        oauth_verifier = self.request.GET['oauth_verifier'];
        
        # Step 3: Once the consumer has redirected the user back to the oauth_callback
        # URL you can request the access token the user has approved. You use the 
        # request token to sign this request. After this is done you throw away the
        # request token and use the access token returned. You should store this 
        # access token somewhere safe, like a database, for future use.
        token = oauth.Token(oauth_token, oauth_token_secret)
        token.set_verifier(oauth_verifier)
        
        client = oauth.Client(consumer, token)
        
        resp, content = client.request(access_token_url, "POST")
        access_token = dict(urlparse.parse_qsl(content))
        
        session['oauth_data'] = access_token
        
        # Redirect to main page
        self.redirect('/')
   
   
class LoginHandler(webapp.RequestHandler):
    def loginToTwitter(self):
        client = oauth.Client(consumer)
        
        # Step 1: Get a request token. This is a temporary token that is used for 
        # having the user authorize an access token and to sign the request to obtain 
        # said access token.
        
        resp, content = client.request(request_token_url, "GET")
        if resp['status'] != '200':
            raise Exception("Invalid response %s." % resp['status'])
        
        request_token = dict(urlparse.parse_qsl(content))
        
        self.response.headers.add_header(
            'Set-Cookie', 
            'oauth_token_secret=%s' \
            % request_token['oauth_token_secret'].encode())
        
        #print "Request Token:"
        #print "    - oauth_token        = %s" % request_token['oauth_token']
        #print "    - oauth_token_secret = %s" % request_token['oauth_token_secret']
        #print 
        
        # Step 2: Redirect to the provider. Since this is a CLI script we do not 
        # redirect. In a web application you would redirect the user to the URL
        # below.
        
        self.redirect("%s?oauth_token=%s" % (authorize_url, request_token['oauth_token']))
            
    def get(self):
        session = get_current_session()
        
        oauth_data = session.get('oauth_data');
        
        if oauth_data == None:
            self.loginToTwitter()
            return
            
        self.redirect('/')
   
        
class LogoutHandler(webapp.RequestHandler):
    def get(self):
        session = get_current_session()
        del session['oauth_data']
        del session['has_list']
        self.redirect('/')
        
        
class UnfollowHandler(webapp.RequestHandler):
    def post(self):
        if is_logged_in() == False:
            self.response.out.write('err')
            return
    
        session = get_current_session()
        
        user_id = self.request.POST['user_id']
        api = get_twitter_api()
        api.destroy_friendship(user_id = user_id)
        
        if 'has_list' in session:
            list_id = session['has_list']
            api.add_list_member('inactive-following', user_id)
        
        self.response.out.write('ok')
        
        
class CreateInactiveListHandler(webapp.RequestHandler):
    def get(self):
        if is_logged_in() == False:
            self.redirect('/login')
            return

        session = get_current_session()
        api = get_twitter_api()
        
        list = None
        
        try:
            list = api.get_list(owner = session['oauth_data']['screen_name'], slug = 'inactive-following')
        except tweepy.TweepError:
            pass
            
        if list == None:
            api.create_list(name = 'Inactive Following', mode = 'private', description = 'Inactive following users')
            
        session['has_list'] = True
            
        self.redirect('/')


def main():
    application = webapp.WSGIApplication([('/', MainHandler),
                                          ('/unfollow', UnfollowHandler),
                                          ('/create_list', CreateInactiveListHandler),
                                          ('/login', LoginHandler),
                                          ('/logout', LogoutHandler),
                                          ('/callback', TwitterOAuthCallbackHandler)],
                                         debug=True)
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()
