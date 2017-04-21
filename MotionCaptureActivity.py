#
# MotionCaptureActivity
# Includes binaries from the tarball at
# http://dev.laptop.org/~quozl/motion-2007-03-05.tar.bz2
# Originally based on information from http://wiki.laptop.org/go/MotionDetection
#
# version 3, 2008-03-22
# 
import pango
import gtk, logging, os, subprocess, sys
import gobject
from sugar.activity import activity
from sugar import network
from os import sep, listdir
import socket
import fcntl
import struct
import urllib2

maxImages = 25
webroot = "/tmp"
cleanUpInterval = 20 * 1000  # in milliseconds
contCapture = True
captStatus = "running"

# http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/439094
def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(
             fcntl.ioctl(
               s.fileno(),
               0x8915,  # SIOCGIFADDR
               struct.pack('256s', ifname[:15])
             )[20:24])

class MotionCaptureActivity(activity.Activity):
    def __init__(self, handle):
        self._debug = True
        self._name = "Motion Capture"
        self._logger = logging.getLogger(self._name)
        if self._debug:
            self._logger.setLevel(logging.DEBUG)
        activity.Activity.__init__(self, handle)
        self._logger.debug("activity running")
        self._httpServer = myHTTPServer(self)
        self.motionStarted = False
        self._displaySetup()
        self.startMotionCapture()
        self.motionStarted = True
        # I intended to use "delete_event", but for some reason that
        # was never triggered. "destroy" does work.
        self.connect("destroy", self.handleDeleteEvent)
        gobject.timeout_add(cleanUpInterval, self.scheduledCleanup)
        self._logger.info("__init__ done")

    def handleDeleteEvent(self, widget):
        self._logger.info("handleDeleteEvent")
        self.stopMotionCapture()
        self._logger.info("handleDeleteEvent - DONE")
        return False

    def _displaySetup(self):
        # Set title
        self.set_title(self._name)
        
        # Attach sugar toolbox
        toolbox = activity.ActivityToolbox(self)
        self.set_toolbox(toolbox)
        toolbox.show()

        self._main_view = gtk.HBox(homogeneous=True)
        
        self.leftBox = gtk.VBox()
        self.centerBox = gtk.VBox(homogeneous=False)
        self.rightBox = gtk.VBox()
        self._main_view.pack_start(self.leftBox, True, True)
        self._main_view.pack_start(self.centerBox)
        self._main_view.pack_start(self.rightBox, True, True)

        self.statusControl = gtk.VBox()
        self.RunPause = gtk.RadioButton(None, "Paused")
        self.RunPause.connect("toggled", self.RunPauseCB, "Pause")
        self.statusControl.pack_start(self.RunPause, False, False, 0)
        self.RunPause.show()

        self.RunPause = gtk.RadioButton(self.RunPause, "Running")
        self.RunPause.set_active(True)
        self.statusControl.pack_start(self.RunPause, False, False, 0)
        self.RunPause.show()

        self.centerBox.pack_start(self.statusControl, False, False)
        self.statusControl.show()

        # centerBox2 has the limitbox and the continuous check box
        self.centerBox2 = gtk.VBox()

        # imgLimit box has a label and a spin_button
        self.imgLimit_box = gtk.HBox()

        self.imgLimit_label = gtk.Label("Maximum captured images:")
        self.imgLimit_box.pack_start(self.imgLimit_label, True, False)
        self.imgLimit_label.show()

        adj = gtk.Adjustment(maxImages, 10, 99, 1, 10)
        self.spin_button = gtk.SpinButton(adj, climb_rate=0.25) 
        self.imgLimit_box.pack_start(self.spin_button, True, False)
        self.spin_button.show()

        self.centerBox2.pack_start(self.imgLimit_box, False, False)
        self.imgLimit_box.show()

        self.contCB = gtk.CheckButton("Capture Continuously")
        self.contCB.connect("toggled", self.contToggle, None)
        self.centerBox2.pack_start(self.contCB, False, False)
        self.contCB.set_active(contCapture)
        self.contCB.show()

        self.centerBox.pack_start(self.centerBox2, True, False)
        self.centerBox2.show()

        # Below centerBox2 is the string that lists the URL for
        # this unit.
        s = """To view the captured images, visit
' http://""" + \
            get_ip_address('eth0') + ":8082/'" + """
using a web browser."""
        self.label1 = gtk.Label(s)
        self.centerBox.pack_start(self.label1, True, True)
        self.label1.show()

#        self.label2 = gtk.Label("""(Live webcam at
#http://""" + get_ip_address('eth0') + ":8081/)")
#        self.centerBox.pack_start(self.label2, True, True)
#        self.label2.show()

        self.leftBox.show()
        self.centerBox.show()
        self.rightBox.show()

        self._main_view.show()
        self.set_canvas(self._main_view)
        self.show_all()
    
    def RunPauseCB(self, widget, data=None):
        self._logger.info("RunPause toggled, data = " + data)
        global captStatus
        if self.motionStarted == True:
            if captStatus == "running":
                urllib2.urlopen("http://localhost:8080/0/detection/pause")
                captStatus = "paused"
            else:
                captStatus = "running"
                if contCapture == False:
                    for file in sorted(listdir(webroot)):
                        if file.endswith(".jpg"):
                            os.remove(webroot + sep + file)
                urllib2.urlopen("http://localhost:8080/0/detection/start")

    def contToggle(self, widget, data=None):
        # callback for the continuous checkbox
        self._logger.info("contToggle")
        global contCapture
        contCapture = widget.get_active()

    def startMotionCapture(self):
        self._logger.info("Starting motion...")
        activityDir = os.environ['SUGAR_BUNDLE_PATH']
        cmd = [ "motion", "-c", activityDir + sep + "motion.conf"]
        self._logger.info("in dir= " + activityDir)
        infoDir = os.path.join(activityDir, "info")
        os.putenv('LD_LIBRARY_PATH',
            os.path.join(activityDir, "lib"))
        retcod = subprocess.call(cmd)
        self._logger.info("motion returned: " + str(retcod))

    def stopMotionCapture(self):
        cmd = [ "killall", "motion" ]
        self._logger.info("killall...")
        subprocess.call(cmd)
        self._logger.info("DONE")

    def scheduledCleanup(self):
        self.cleanUpDir()
        # Cleanup must be rescheduled after each timeout
        gobject.timeout_add(cleanUpInterval, self.scheduledCleanup)

    def cleanUpDir(self):
        # Limit the number of pictures...
        # The following loop assumes the file names are date stamps
        global maxImages
        global contCapture
        self.count = 0
        self._logger.info("Cleaning up...")
        maxImages = self.spin_button.get_value_as_int()
        fileList=[]
        for file in sorted(listdir(webroot)):
            if file.endswith(".jpg"):
                fileList.append(file)
        if contCapture:
            fileList.reverse()
        else:
            if len(fileList) >= maxImages:
                urllib2.urlopen("http://localhost:8080/0/detection/pause")

        for file in fileList:
            if self.count < maxImages:
                self.count += 1
            else:
                os.remove(webroot + sep + file)

class myHTTPServer(network.GlibTCPServer):
    def __init__(self, pca):
        self.ca = pca
        server_address = ("", 8082)
        network.GlibTCPServer.__init__(self, server_address, myHandler)

class myHandler(network.ChunkedGlibHTTPRequestHandler):

    def myStdHeader(self):
        self.send_response(200)
        self.send_header('Content-type','text/html')
        self.end_headers()

    def myNavigation(self, page):
        # links at top of page
        if page != "Live":
            self.wfile.write('<a href="webcam.html">Live View</a> ')
        else:
            self.wfile.write('Live View ')
        if page != "Images":
            self.wfile.write('<a href="images.html">Images</a> ')
        else:
            self.wfile.write('Images ')
        if page != "Controls":
            self.wfile.write('<a href="controls.html">Controls</a> ')
        else:
            self.wfile.write('Controls ')
        self.wfile.write('<br><hr>')

    def do_GET(self):
        global captStatus
        self.count = 0
        try:
            if self.path == "/controls.html":
                self.myStdHeader()
                self.wfile.write('<head>')
                self.wfile.write('<link rel="shortcut icon" href="/favicon.ico" />')
                self.wfile.write('</head>')
                self.myNavigation("Controls")
                self.wfile.write(
                'See the <a href="http://www.lavrsen.dk/twiki/bin/view/Motion/MotionGuideAlphabeticalOptionReferenceManual">')
                self.wfile.write('Motion Reference Manual<a> for defintions.<br>')

                self.wfile.write('<iframe src="http://' \
                    + get_ip_address('eth0') + ':8080/0/" width="360" \
                    height="500"> \
                    Controls</iframe>')
                return

            if self.path == "/webcam.html":
                self.myStdHeader()
                self.wfile.write('<head>')
                self.wfile.write('<link rel="shortcut icon" href="/favicon.ico" />')
                self.wfile.write('</head>')
                self.myNavigation("Live")
                self.wfile.write('(Refresh if not updating.)<br>')
                self.wfile.write('<iframe src="http://' \
                    + get_ip_address('eth0') + ':8081/" width="660" \
                    height="500">Webcam</iframe>')
                return

            # show thumbnails
            if self.path == "/images.html" or self.path == "/" \
               or self.path == "/index.html":
                self.myStdHeader()
                self.wfile.write('<head>')
                self.wfile.write('<meta http-equiv="refresh" content="10"')
                self.wfile.write(';url=images">\n')
                self.wfile.write('<link rel="shortcut icon" href="/favicon.ico" />')
                self.wfile.write('<script language="JavaScript">\n<!--\n')

                imgTags=""
                preload=""
                fileList=[]
                for file in sorted(listdir(webroot)):
                    if file.endswith(".jpg"):
                        fileList.append(file)
                if len(fileList) >= maxImages:
                    if contCapture:
                        fileList = fileList[(len(fileList) - maxImages):]
                    else:
                        urllib2.urlopen("http://localhost:8080/0/detection/pause")
                        fileList = fileList[:maxImages]

                fileList.reverse()
                for file in fileList:
                    self.count += 1
                    imgTags += '<span>'
                    imgTags += '<a href="' + file + '.html">'
                    imgTags += '<img border="0" src="' + file
                    imgTags += '" width="160" height="120"></a>'
                    imgTags += '</span>'
                    preload += 'pic' + str(self.count)
                    preload += ' = new Image(120,160);\n'
                    preload += 'pic' + str(self.count) + '.src'
                    preload += '="' + file + '";\n'
                self.wfile.write(preload)
                self.wfile.write('//--></script>')
                self.wfile.write('</head>')
                self.wfile.write('<body>')
                self.myNavigation("Images")
                if self.count >= maxImages and not contCapture :
                    self.wfile.write('Captured ' + str(maxImages) + ' images. ')
                    self.wfile.write('<a href="deleteAll">Restart?</a>')
                elif self.count < maxImages:
                    self.wfile.write('Captured ' + str(self.count) + ' of ' + str(maxImages) + ' images.')
                else :
                    self.wfile.write('Last ' + str(maxImages) + ' capture images. ')
                self.wfile.write('<br><br>(Click on an image for full-size.)<br>')
                self.wfile.write(imgTags)
                self.wfile.write('</body>')
                return

            if self.path.endswith(".jpg.html"):
                self.myStdHeader()
                self.wfile.write('<head>')
                self.wfile.write('<link rel="shortcut icon" href="/favicon.ico" />')
                self.wfile.write('</head>')
                self.myNavigation(None)
                self.wfile.write('<img border="0" src="' + self.path[:-5] + '">')
                self.wfile.write('<a href="' + self.path[:-5]  +'?delete">')
                self.wfile.write('Delete</a>')
                return

            if self.path.endswith("favicon.ico"):
                activityDir = os.environ['SUGAR_BUNDLE_PATH']
                f = open(activityDir + sep + 'www' + sep + 'favicon.png')
                self.send_response(200)
                self.send_header('Content-type','image/png')
                self.send_header('Cache-Control', 'max-age=360000')
                self.end_headers()
                self.wfile.write(f.read())
                f.close()
                return

            if self.path.endswith(".jpg"):
                f = open(webroot + sep + self.path)
                self.send_response(200)
                self.send_header('Content-type','image/jpeg')
                self.send_header('Cache-Control', 'max-age=360000')
                self.end_headers()
                self.wfile.write(f.read())
                f.close()
                return

            if self.path.endswith("deleteAll"):
                for file in sorted(listdir(webroot)):
                    if file.endswith(".jpg"):
                        os.remove(webroot + sep + file)
                self.send_response(200)
                self.send_header('Content-type','text/html')
                self.end_headers()
                self.wfile.write("""
                <head>
                <meta http-equiv="refresh" content="0;url=images.html">
                </head>
                """)
                if captStatus == "running":
                    urllib2.urlopen("http://localhost:8080/0/detection/start")
                return

            if self.path.endswith(".jpg?delete"):
                os.remove(webroot + sep + self.path.replace('?delete',''))
                self.send_response(200)
                self.send_header('Content-type','text/html')
                self.end_headers()
                self.wfile.write("""
                <head>
                <meta http-equiv="refresh" content="1;url=images.html">
                </head>
                """)
                self.wfile.write("Deleted: " + self.path.replace('?delete',''))
                if captStatus == "running":
                    urllib2.urlopen("http://localhost:8080/0/detection/start")
                return

            self.send_error(404,'File Not Found: %s' % self.path)
            return
                
        except IOError:
            self.send_error(404,'File Not Found: %s' % self.path)

