import re
import cgi
import urllib
import wsgiref.handlers

from math import log
from google.appengine.ext        import webapp
from google.appengine.ext        import db
from google.appengine.api        import urlfetch
from google.appengine.ext.webapp import template
from google.appengine.api.urlfetch_errors import *

# TODO: Need to define a word properly. Use Porter stemming algorithm here.
wordre = re.compile("[^A-Za-z]")
def words(text):
    """Split a string into a list of words. Converts to lowercase."""
    return [ w for w in wordre.split(text.lower()) if w and re.match('[a-z]', w)]

def freq(words):
    """Returns the frequency of words as a dict, given a list of words"""
    f = {}
    for i in words: f[i] = f.get(i,0) + 1
    return f

def siw(textfreq, corpfreq={}):
    """Returns the relative probability of each word w.r.t the corpus. Scales results to a maximum of 1.0"""
    siw = {}
    max = 0
    for word in textfreq:
        cf = float(corpfreq.get(word, 1))
        siw[word] = prob = textfreq[word] / cf
        if (max < prob): max = prob
    for word in textfreq: siw[word] = siw[word] / max
    return siw

def loadfreq(file):
    """Returns the frequency of words in the file"""
    freq = {}
    for line in open(file):
        words = line.rstrip().split()
        freq[words[0]] = float(words[1])
    return freq

class URLLog(db.Model):
  url = db.StringProperty()
  date = db.DateTimeProperty(auto_now_add=True)

class ErrorLog(db.Model):
  url = db.StringProperty()
  error = db.StringProperty()
  date = db.DateTimeProperty(auto_now_add=True)


# """ Dummy class created only for testing. Mimics a result"""
# class DummyResult:
#     status_code = 200
#     content = open("sample.txt").read()

class SIW(webapp.RequestHandler):
    def get(self):
        url = self.request.get('url')
        if not url:
            urls = list(set(v.url for v in db.GqlQuery("SELECT * FROM URLLog ORDER BY date DESC LIMIT 10")))
            self.response.out.write(template.render('index.html', {'urls': urls, 'usestop': 0}))
        else:
            url = url.strip()
            usestop = self.request.get('usestop')
            URLLog(url=url).put()
            try:
                result = urlfetch.fetch("http://cgi.w3.org/cgi-bin/html2txt?noinlinerefs=on&nonums=on&url=" + urllib.quote(url))
                # result = DummyResult()
                if result.status_code == 200:
                    alt = self.request.get('alt')
                    corpfreq = loadfreq('corpus.txt')
                    stopword = dict( [v,1] for v in open('stopwords.txt').read().split() )

                    text = re.sub(r'\[[^\]]*\]', '', result.content)    # Remove all sqare brackets. html2txt introduces too many of those
                    textfreq = freq(words(text))
                    textprob = siw(textfreq, corpfreq)

                    self.pieces = []
                    wordlist = sorted(textfreq.keys())
                    showallwords = len(wordlist) < 500
                    max_fr = 0
                    for word in wordlist:
                        if not usestop and (stopword.get(word,0) or len(word) <= 2): continue
                        wordfreq = textfreq[word]
                        wordprob = textprob[word]
                        if showallwords or wordfreq > 1:
                            if max_fr < wordfreq: max_fr = wordfreq
                            self.pieces.append(self.format(alt, word, wordfreq, wordprob))
                    if alt == 'html': self.response.out.write(" ".join(self.pieces))
                    else: self.response.out.write(template.render('index.html', dict(url=url, usestop=usestop, max_fr=max_fr, text=re.sub(r'\s+', ' ', text.replace('\\', '\\\\').replace('"', '\\"')), html=" ".join(self.pieces))))
                else:
                    self.response.out.write(template.render('index.html', dict(url=url, usestop=usestop, max_fr=0, text='', html="Unable to open " + url )))
            except Exception, e:
                ErrorLog(url=url, error=repr(e)).put()
                self.response.out.write(template.render('index.html', { 'url': url, 'usestop': usestop, 'html': "<b>Unable to fetch the URL. Please try a different URL.</b><br/>This is often because the page takes much more than 1 second to load.<br/><pre>" + repr(e) + "</pre>" }))

    def colsize(self, wordfreq, wordprob):
        return (int(255 * (1-pow(wordprob,0.15))), int(10 * log(wordfreq) + 15))

    def format(self, alt, word, wordfreq, wordprob):
        if not alt or alt == "html":
            color, size = self.colsize(wordfreq, wordprob)
            string = "<span style='color:#" + hex(color).lstrip('0x').zfill(2) * 3 + ";font-size:" + str(size) + "px'"
            if not alt: string = string + " fr='" + str(wordfreq) + "' pr='" + str(wordprob) + "'"
            string = string + ">" + word + "</span>"
        return string

if __name__ == '__main__':
    application = webapp.WSGIApplication([('/', SIW)], debug=True)
    wsgiref.handlers.CGIHandler().run(application)
