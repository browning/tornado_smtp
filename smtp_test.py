import smtpserver
import tornado.ioloop
import email

def handle_msg(msg):
    print "##### NEW MESSAGE ####"
    print "from: " + msg['from']
    print "subject: " + msg['subject']
    x = email.iterators.body_line_iterator(msg)
    for line in x:
        print line

smtp_server = smtpserver.SMTPServer(handle_msg)
smtp_server.listen(25)
tornado.ioloop.IOLoop.instance().start()

