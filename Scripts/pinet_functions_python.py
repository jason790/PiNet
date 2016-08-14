#! /usr/bin/env python3
# Part of PiNet https://github.com/pinet/pinet
#
# See LICENSE file for copyright and license details

# PiNet
# pinet_functions_python.py
# Written by Andrew Mulholland
# Supporting python functions for the main pinet script in BASH.
# Written for Python 3.4

# PiNet is a utility for setting up and configuring a Linux Terminal Server Project (LTSP) network for Raspberry Pi's

import crypt
import csv
import errno
import grp
import logging
import os
import os.path
import pickle
import pwd
import random
import re
import shutil
import socket
import sys
import time
import traceback
import urllib.error
import urllib.request
import xml.etree.ElementTree
from logging import debug, info
from subprocess import Popen, PIPE, check_output, CalledProcessError
from xml.dom import minidom

import feedparser
import requests


# basicConfig(level=WARNING)


# from gettext import gettext as _
# gettext.textdomain(pinetPython)


# Set up message catalog access
# t = gettext.translation('pinetPython', 'locale', fallback=True)
# _ = t.ugettext

def _(placeholder):
    # GNU Gettext placeholder
    return (placeholder)


RepositoryBase = "https://github.com/pinet/"
RepositoryName = "pinet"
BootRepository = "PiNet-Boot"
RawRepositoryBase = "https://raw.github.com/pinet/"
Repository = RepositoryBase + RepositoryName
RawRepository = RawRepositoryBase + RepositoryName
RawBootRepository = RawRepositoryBase + BootRepository
ReleaseBranch = "master"
configFileData = {}
fileLogger = None


class softwarePackage():
    """
    Class for software packages.
    """

    name = ""
    description = ""
    installType = ""
    installCommands = None
    marked = False
    installOnServer = False
    parameters = ()

    def __init__(self, name, installType, installCommands=None, description="", installOnServer=False, parameters=()):
        super(softwarePackage, self).__init__()
        self.name = name
        self.description = description
        self.installType = installType
        self.installCommands = installCommands
        self.installOnServer = installOnServer
        self.parameters = parameters

    def installPackage(self):
        debug("Installing " + self.name)
        debug(self.installCommands)
        if isinstance(self.installCommands, list) and len(self.installCommands) > 0:
            programs = " ".join(self.installCommands)
        elif self.installCommands is None:
            programs = self.name
        else:
            programs = self.installCommands
        if self.installType == "pip":
            self.marked = False
            if self.installOnServer:
                runBash("pip install -U " + programs)
                runBash("pip3 install -U " + programs)
            else:
                ltspChroot("pip install -U " + programs)
                ltspChroot("pip3 install -U " + programs)
            return
        elif self.installType == "apt":
            self.marked = False
            installAptPackage(programs, installOnServer=self.installOnServer, parameters=self.parameters)
        elif self.installType == "script":
            for i in self.installCommands:
                runBash("ltsp-chroot --arch armhf " + i)
            self.marked = False
        elif self.installType == "epoptes":
            installEpoptes()
        elif self.installType == "scratchGPIO":
            installScratchGPIO()
        else:
            print(_("Error in installing") + " " + self.name + " " + _("due to invalid install type."))
            self.marked = False

    def customAptPip(self):
        done = False
        while done == False:
            if self.installType == "customApt":
                packageName = whiptailBox("inputbox", _("Custom package"),
                                          _("Enter the name of the name of your package from apt you wish to install."),
                                          False, returnErr=True)
                if packageName == "":
                    yesno = whiptailBox("yesno", _("Are you sure?"),
                                        _("Are you sure you want to cancel the installation of a custom apt package?"),
                                        True)
                    if yesno:
                        self.marked = False
                        done = True
                        # else:
                        # print("Setting marked to false")
                        # self.marked = False
                else:
                    self.installType = "apt"
                    self.installCommands = [packageName, ]
                    self.marked = True
                    done = True

            elif self.installType == "customPip":
                packageName = whiptailBox("inputbox", _("Custom Python package"), _(
                    "Enter the name of the name of your python package from pip you wish to install."), False,
                                          returnErr=True)
                if packageName == "":
                    yesno = whiptailBox("yesno", _("Are you sure?"),
                                        _("Are you sure you want to cancel the installation of a custom pip package?"),
                                        True)
                    if yesno:
                        self.marked = False
                        done = True
                    else:
                        self.marked = False
                else:
                    self.installType = "pip"
                    self.installCommands = [packageName, ]
                    self.marked = True
                    done = True
            else:
                self.marked = True
                done = True


def setupLogger():
    global fileLogger
    fileLogger = logging.getLogger()
    handler = logging.FileHandler('/var/log/pinet.log')
    formatter = logging.Formatter(
        '%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
    handler.setFormatter(formatter)
    fileLogger.addHandler(handler)
    fileLogger.setLevel(logging.DEBUG)


def runBashOld(command, checkFailed=False):
    # Deprecated in favor of new runBash
    if type(command) == str:
        p = Popen("sudo " + command, shell=True)
        p.wait()
        returnCode = p.returncode
    else:
        p = Popen(command)
        p.wait()
        returnCode = p.returncode
    if checkFailed:
        if int(returnCode) != 0:
            fileLogger.warning("Command \"" + command + "\" failed to execute correctly with a return code of " + str(
                returnCode) + ".")
            continueOn = whiptailBoxYesNo(_("Command failed to execute"), _(
                "Command \"" + command + "\" failed to execute correctly with a return code of " + str(
                    returnCode) + ". Would you like to continue and ignore the error or retry the command?"),
                                          returnTrueFalse=True, customYes=_("Continue"), customNo=_("Retry"),
                                          height="9")
            if continueOn:
                fileLogger.info("Failed command \"" + command + "\" was ignored and program continued.")
                return returnCode
            else:
                runBash(command, True)
    else:
        fileLogger.debug("Command \"" + command + "\" executed successfully.")
        return returnCode


def runBashOutput(command):
    # Deprecated in favor of new runBash
    output = check_output("sudo " + command, shell=True)
    return output


def runBash(command, returnStatus=True, runAsSudo=True, returnString=False, ignoreErrors=False):
    """
    Run a Bash command from Python and get back its return code or returned string.

    :param command: Bash command to be executed in a string or list form.
    :param returnStatus: Whether to return the status (as boolean).
    :param runAsSudo: Should sudo be prefixed onto the command.
    :param returnString: Whether the actual command response string should be returned.
    :param ignoreErrors: Set to True to ignore a non 0 return code.
    :return: Return code or returned string.
    """
    try:
        if isinstance(command, str):
            shell = True
            if runAsSudo:
                command = "sudo " + command
            else:
                command = (["sudo"] + command)
        elif isinstance(command, list):
            shell = False
        else:
            return None
        if returnString:
            commandOutput = check_output(command, shell=shell)
            fileLogger.debug("Command \"" + command + "\" executed successfully.")
            return commandOutput.decode()
        else:
            p = Popen(command, shell=shell)
            p.wait()
            returnCode = p.returncode
            if returnCode != 0:
                raise CalledProcessError(returnCode, str(command))
            fileLogger.debug("Command \"" + command + "\" executed successfully.")
            return True
    except CalledProcessError as c:
        fileLogger.warning("Command \"" + command + "\" failed to execute correctly with a return code of " + str(
            c.returncode) + ".")
        if ignoreErrors == False:
            continueOn = whiptailBoxYesNo(_("Command failed to execute"), _(
                "Command \"" + command + "\" failed to execute correctly with a return code of " + str(
                    c.returncode) + ". Would you like to continue and ignore the error or retry the command?"),
                                          returnTrueFalse=True, customYes=_("Continue"), customNo=_("Retry"),
                                          height="11")
            if continueOn:
                fileLogger.info("Failed command \"" + command + "\" was ignored and program continued.")
                return c.returncode
            else:
                return runBash(command, returnStatus=returnStatus, runAsSudo=runAsSudo, returnString=returnString)
        else:
            return c.returncode


def getUsers(includeRoot=False):
    users = []
    for p in pwd.getpwall():
        if (len(str(p[2])) > 3) and (str(p[5])[0:5] == "/home"):  # or (str(p[5])[0:5] == "/root"):
            users.append(p[0].lower())
    return users


def ltspChroot(command, returnStatus=True, returnString=False):
    runBash("ltsp-chroot --arch armhf " + command, runAsSudo=True, returnStatus=returnStatus, returnString=returnString)


def installAptPackage(toInstall, update=False, upgrade=False, installOnServer=False, parameters=()):
    parameters = " ".join(parameters)
    if update:
        runBash("apt-get update")
    if upgrade:
        runBash("apt-get upgrade -y")
    if installOnServer:
        runBash("apt-get install -y " + parameters + " " + str(toInstall))
    else:
        ltspChroot("apt-get install -y " + parameters + " " + str(toInstall))


def createTextFile(location, text):
    newText = text.split("\n")
    newText = stripStartWhitespaces(newText)
    newText = stripEndWhitespaces(newText)
    writeTextFile(newText, location)


def makeFolder(directory):
    if not os.path.exists(directory):
        fileLogger.debug("Creating directory - " + str(directory))
        os.makedirs(directory)


def getReleaseChannel():
    Channel = "Stable"
    configFile = getList("/etc/pinet")
    for i in range(0, len(configFile)):
        if configFile[i][0:14] == "ReleaseChannel":
            Channel = configFile[i][15:len(configFile[i])]
            break

    global ReleaseBranch
    Channel = Channel.lower()
    if Channel == "stable":
        ReleaseBranch = "master"
    elif Channel == "dev":
        ReleaseBranch = "dev"
    elif len(Channel) > 7 and Channel[0:7].lower() == "custom:":
        ReleaseBranch = Channel[7:len(Channel)]
    else:
        ReleaseBranch = "master"


def getTextFile(filep):
    """
    Opens the text file and goes through line by line, appending it to the filelist list.
    Each new line is a new object in the list, for example, if the text file was
    ----
    hello
    world
    this is an awesome text file
    ----
    Then the list would be
    ["hello", "world", "this is an awesome text file"]
    Each line is a new object in the list

    """
    if not os.path.exists(filep):
        return []
    file = open(filep)
    filelist = []
    while 1:
        line = file.readline()
        if not line:
            break
        filelist.append(line)
    return filelist


def removeN(filelist):
    """
    Removes the final character from every line, this is always /n, aka newline character.
    """
    for count in range(0, len(filelist)):
        filelist[count] = filelist[count][0: (len(filelist[count])) - 1]
    return filelist


def blankLineRemover(filelist):
    """
    Removes blank lines in the file.
    """
    toremove = []
    # toremove.append(len(filelist))
    for count in range(0, len(filelist)):  # Go through each line in the text file
        found = False
        for i in range(0, len(filelist[count])):  # Go through each char in the line
            if not (filelist[count][i] == " "):
                found = True
        if found == False:
            toremove.append(count)

    # toremove.append(len(filelist))
    toremove1 = []
    for i in reversed(toremove):
        toremove1.append(i)

    for r in range(0, len(toremove)):
        filelist.pop(toremove1[r])
        debug("just removed " + str(toremove1[r]))
    return filelist


def writeTextFile(filelist, name):
    """
    Writes the final list to a text file.
    Adds a newline character (\n) to the end of every sublist in the file.
    Then writes the string to the text file.
    """
    file = open(name, 'w')
    mainstr = ""
    for i in range(0, len(filelist)):
        mainstr = mainstr + filelist[i] + "\n"
    file.write(mainstr)
    file.close()
    info("")
    info("------------------------")
    info("File generated")
    info("The file can be found at " + name)
    info("------------------------")
    info("")


def getList(file):
    """
    Creates list from the passed text file with each line a new object in the list
    """
    return removeN(getTextFile(file))


def checkStringExists(filename, toSearchFor):
    textFile = getList(filename)
    unfound = True
    for i in range(0, len(textFile)):
        found = textFile[i].find(toSearchFor)
        if (found != -1):
            unfound = False
            break
    if unfound:
        return False

    return True


def findReplaceAnyLine(textFile, string, newString):
    """
    Basic find and replace function for entire line.
    Pass it a text file in list form and it will search for strings.
    If it finds a string, it will replace the entire line with newString
    """
    unfound = True
    for i in range(0, len(textFile)):
        found = textFile[i].find(string)
        if (found != -1):
            textFile[i] = newString
            unfound = False
    if unfound:
        textFile.append(newString)

    return textFile


def findReplaceSection(textFile, string, newString):
    """
    Basic find and replace function for section.
    Pass it a text file in list form and it will search for strings.
    If it finds a string, it will replace that exact string with newString
    """
    for i in range(0, len(textFile)):
        found = textFile[i].find(string)
        if (found != -1):
            before = textFile[i][0:found]
            after = textFile[i][found + len(string):len(textFile[i])]
            textFile[i] = before + newString + after
    return textFile


def downloadFile(url, saveloc):
    """
    Downloads a file from the internet using a standard browser header.
    Custom header is required to allow access to all pages.
    """
    try:
        req = urllib.request.Request(url)
        req.add_header('User-agent', 'Mozilla 5.10')
        f = urllib.request.urlopen(req)
        text_file = open(saveloc, "wb")
        text_file.write(f.read())
        text_file.close()
        fileLogger.debug("Downloaded file from " + url + " to " + saveloc + ".")
        return True
    except urllib.error.URLError as e:
        fileLogger.debug("Failed to download file from " + url + " to " + saveloc + ". Error was " + e.reason)
    except:
        print(traceback.format_exc())
        fileLogger.debug("Failed to download file from " + url + " to " + saveloc + ".")
        return False


# def downloadFile(url, saveloc):
#    import requests
#    r = requests.get(url)
#    with open("code3.zip", "wb") as code:
#        code.write(r.content)


def stripStartWhitespaces(filelist):
    """
    Remove whitespace from start of every line in list.
    """
    for i in range(0, len(filelist)):
        filelist[i] = str(filelist[i]).lstrip()
    return filelist


def stripEndWhitespaces(filelist):
    """
    Remove whitespace from end of every line in list.
    """
    for i in range(0, len(filelist)):
        filelist[i] = str(filelist[i]).rstrip()
    return filelist


def cleanStrings(filelist):
    """
    Removes \n and strips whitespace from before and after each item in the list
    """
    filelist = removeN(filelist)
    filelist = stripStartWhitespaces(filelist)
    return stripEndWhitespaces(filelist)


def getCleanList(filep):
    return cleanStrings(getTextFile(filep))


def compareVersions(local, web):
    """
    Compares 2 version numbers to decide if an update is required.
    """
    web = str(web).split(".")
    local = str(local).split(".")
    if int(web[0]) > int(local[0]):
        returnData(1)
        return True
    else:
        if int(web[1]) > int(local[1]):
            returnData(1)
            return True
        else:
            if int(web[2]) > int(local[2]):
                returnData(1)
                return True
            else:
                returnData(0)
                return False


def getConfigParameter(filep, searchfor, break_on_first_find=False):
    textFile = getTextFile(filep)
    textFile = stripEndWhitespaces(textFile)
    value = ""
    for i in range(0, len(textFile)):
        found = textFile[i].find(searchfor)
        if (found != -1):
            value = textFile[i][found + len(searchfor):len(textFile[i])]
            if break_on_first_find:
                break

    if value == "":
        value = "None"

    return value


def setConfigParameter(option, value, filep="/etc/pinet"):
    newValue = option + "=" + value
    replaceLineOrAdd(filep, option, newValue)


def returnData(data):
    with open("/tmp/ltsptmp", "w+") as text_file:
        text_file.write(str(data))
    return


def readReturn():
    with open("/tmp/ltsptmp", "r") as text_file:
        print(text_file.read())


def removeFile(file):
    try:
        shutil.rmtree(file)
        fileLogger.debug("File at " + file + " has been deleted.")
    except (OSError, IOError):
        pass


def copyFileFolder(src, dest):
    try:
        shutil.copytree(src, dest)
        fileLogger.debug("File/folder has been copied from " + src + " to " + dest + ".")
    except OSError as e:
        # If the error was caused because the source wasn't a directory
        if e.errno == errno.ENOTDIR:
            shutil.copy(src, dest)
        else:
            print('Directory not copied. Error: %s' % e)
            fileLogger.debug('Directory not copied. Error: %s' % e)


# ----------------Whiptail functions-----------------
def whiptailBox(whiltailType, title, message, returnTrueFalse, height="8", width="78", returnErr=False, other=""):
    cmd = ["whiptail", "--title", title, "--" + whiltailType, message, height, width, other]
    p = Popen(cmd, stderr=PIPE)
    out, err = p.communicate()

    if returnTrueFalse:
        if p.returncode == 0:
            return True
        elif p.returncode == 1:
            return False
        else:
            return "ERROR"
    elif returnErr:
        return err.decode()
    else:
        return p.returncode


def whiptailSelectMenu(title, message, items, height="16", width="78", other="5"):
    cmd = ["whiptail", "--title", title, "--menu", message, height, width, other]
    itemsList = ""
    for x in range(0, len(items)):
        cmd.append(items[x])
        cmd.append("a")
    cmd.append("--noitem")
    p = Popen(cmd, stderr=PIPE)
    out, err = p.communicate()
    returnCode = p.returncode
    if str(returnCode) == "0":
        return (err)
    else:
        return ("Cancel")


def whiptailCheckList(title, message, items):
    height, width, other = "20", "100", str(len(items))  # "16", "78", "5"
    cmd = ["whiptail", "--title", title, "--checklist", message, height, width, other]
    itemsList = ""
    for x in range(0, len(items)):
        cmd.append(items[x][0])
        cmd.append(items[x][1])
        cmd.append("OFF")
    p = Popen(cmd, stderr=PIPE)
    out, err = p.communicate()
    returnCode = p.returncode
    if str(returnCode) == "0":
        return (err)
    else:
        return ("Cancel")


def whiptailBoxYesNo(title, message, returnTrueFalse, height="8", width="78", returnErr=False, customYes="",
                     customNo=""):
    cmd = ["whiptail", "--yesno", "--title", title, message, height, width,
           "--yes-button", customYes,
           "--no-button", customNo]
    p = Popen(cmd, stderr=PIPE)
    out, err = p.communicate()

    if returnTrueFalse:
        if p.returncode == 0:
            return True
        elif p.returncode == 1:
            return False
        else:
            return "ERROR"
    elif returnErr:
        return err.decode()
    else:
        return p.returncode


# ---------------- Main functions -------------------


def replaceLineOrAdd(file, string, newString):
    """
    Basic find and replace function for entire line.
    Pass it a text file in list form and it will search for strings.
    If it finds a string, it will replace that entire line with newString
    """
    textfile = getList(file)
    textfile = findReplaceAnyLine(textfile, string, newString)
    writeTextFile(textfile, file)


def replaceBitOrAdd(file, string, newString):
    """
    Basic find and replace function for section.
    Pass it a text file in list form and it will search for strings.
    If it finds a string, it will replace that exact string with newString
    """
    textfile = getList(file)
    textfile = findReplaceSection(textfile, string, newString)
    writeTextFile(textfile, file)


def internet_on(timeoutLimit=5, returnType=True):
    """
    Checks if there is an internet connection.
    If there is, return a 0, if not, return a 1
    """
    try:
        response = urllib.request.urlopen('http://www.google.com', timeout=int(timeoutLimit))
        returnData(0)
        # print("returning 0")
        return True
    except:
        pass
    try:
        response = urllib.request.urlopen('http://mirrordirector.raspbian.org/', timeout=int(timeoutLimit))
        returnData(0)
        # print("returning 0")
        return True
    except:
        pass
    try:
        response = urllib.request.urlopen('http://18.62.0.96', timeout=int(timeoutLimit))
        returnData(0)
        # print("returning 0")
        return True
    except:
        pass
    # print("Reached end, no internet")
    returnData(1)
    return False


def internet_on_Requests(timeoutLimit=3, returnType=True):
    try:
        response = requests.get("http://archive.raspbian.org/raspbian.public.key", timeout=timeoutLimit)
        if response.status_code == requests.codes.ok:
            returnData(0)
            return True
    except (requests.ConnectionError, requests.Timeout):
        pass
    try:
        response = requests.get("http://archive.raspberrypi.org/debian/raspberrypi.gpg.key", timeout=timeoutLimit)
        if response.status_code == requests.codes.ok:
            returnData(0)
            return True
    except (requests.ConnectionError, requests.Timeout):
        pass
    returnData(1)
    return False


def testSiteConnection(siteURL, timeoutLimit=5):
    """
    Tests to see if can access the given website.
    """
    try:
        response = urllib.request.urlopen(siteURL, timeout=int(timeoutLimit))
        return True
    except:
        return False


def internetFullStatusReport(timeoutLimit=5, whiptail=False, returnStatus=False):
    """
    Full check of all sites used by PiNet. Only needed on initial install
    """
    sites = []
    sites.append(
        [_("Main Raspbian repository"), "http://archive.raspbian.org/raspbian.public.key", ("Critical"), False])
    sites.append([_("Raspberry Pi Foundation repository"), "http://archive.raspberrypi.org/debian/raspberrypi.gpg.key",
                  ("Critical"), False])
    sites.append([_("Github"), "https://github.com", ("Critical"), False])
    sites.append([_("Bit.ly"), "http://bit.ly", ("Highly recommended"), False])
    sites.append([_("Bitbucket (Github mirror, not active yet)"), "https://bitbucket.org", ("Recommended"), False])
    # sites.append([_("BlueJ"), "http://bluej.org", ("Recommended"), False])
    sites.append([_("PiNet metrics"), "https://secure.pinet.org.uk", ("Recommended"), False])
    for website in range(0, len(sites)):
        sites[website][3] = testSiteConnection(sites[website][1])
    if returnStatus:
        return sites
    if whiptail:
        message = ""
        for website in sites:
            if sites[3]:
                status = "Success"
            else:
                status = "Failed"
            message = message + status + " - " + website[2] + " - " + website[0] + " (" + website[1] + ")\n"
            if (shutil.get_terminal_size()[0] < 105) or (shutil.get_terminal_size()[0] < 30):
                print("\x1b[8;30;105t")
                time.sleep(0.05)
        whiptailBox("msgbox", "Web filtering test results", message, True, height="14", width="100")
    else:
        for website in range(0, len(sites)):
            print(str(sites[website][2] + " - "))


def internetFullStatusCheck(timeoutLimit=5):
    results = internetFullStatusReport(timeoutLimit=timeoutLimit, returnStatus=True)
    for site in results:
        if site[2] == "Critical":
            if site[3] == False:
                whiptailBox("msgbox", _("Unable to proceed"), _(
                    "The requested action is unable to proceed as PiNet is not able to access a critical site. Perhaps your internet connection is not active or a proxy or web filtering system may be blocking access. The critical domain that is unable to be accessed is - " +
                    site[1]), False, height="11")
                returnData(1)
                return False
        elif site[2] == "Highly recommended":
            if site[3] == False:
                answer = whiptailBox("yesno", _("Proceeding not recommended"), _(
                    "A highly recommended site is inaccessible. Perhaps a proxy or web filtering system may be blockeing access. Would you like to proceed anyway? (not recommended). The domain that is unable to be accessed is - " +
                    site[1]), True, height="11")
                if answer == False:
                    returnData(1)
                    return False
        elif site[2] == "Recommended":
            if site[3] == False:
                answer = whiptailBox("yesno", _("Proceeding not recommended"), _(
                    "A recommended site is inaccessible. Perhaps a proxy or web filtering system may be blockeing access. Would you like to proceed anyway? (not recommended). The domain that is unable to be accessed is - " +
                    site[1]), True, height="11")
                if answer == False:
                    returnData(1)
                    return False
        else:
            print("Unknown site type...")
    returnData(0)
    return True


def updatePiNet():
    """
    Fetches most recent PiNet and PiNet_functions_python.py
    """
    try:
        os.remove("/home/" + os.environ['SUDO_USER'] + "/pinet")
    except:
        pass
    print("")
    print("----------------------")
    print(_("Installing update"))
    print("----------------------")
    print("")
    download = True
    if not downloadFile(RawRepository + "/" + ReleaseBranch + "/pinet", "/usr/local/bin/pinet"):
        download = False
    if not downloadFile(RawRepository + "/" + ReleaseBranch + "/Scripts/pinet_functions_python.py",
                        "/usr/local/bin/pinet_functions_python.py"):
        download = False
    if download:
        print("----------------------")
        print(_("Update complete"))
        print("----------------------")
        print("")
        returnData(0)
    else:
        print("")
        print("----------------------")
        print(_("Update failed..."))
        print("----------------------")
        print("")
        returnData(1)


def checkUpdate2():
    """
    Grabs the xml commit log to check for releases. Picks out most recent release and returns it.
    """

    loc = "/tmp/raspiupdate.txt"
    downloadFile("http://bit.ly/pinetcheckmaster", loc)
    xmldoc = minidom.parse(loc)
    version = xmldoc.getElementsByTagName('title')[1].firstChild.nodeValue
    version = cleanStrings([version, ])[0]
    if version.find("Release") != -1:
        version = version[8:len(version)]
        print(version)
    else:
        print(_("ERROR"))
        print(_("No release update found!"))


def GetVersionNum(data):
    for i in range(0, len(data)):
        line = data[i][0:8]
        if data[i][0:7] == "Release":
            line = data[i]
            version = str(data[i][8:len(data[i])]).rstrip()
            return version


def checkUpdate(currentVersion):
    if not internet_on(5, False):
        print(_("No Internet Connection"))
        returnData(0)
    downloadFile("http://bit.ly/pinetCheckCommits", "/dev/null")
    d = feedparser.parse(Repository + '/commits/' + ReleaseBranch + '.atom')
    releases = []
    data = (d.entries[0].content[0].get('value'))
    data = ''.join(xml.etree.ElementTree.fromstring(data).itertext())
    data = data.split("\n")
    thisVersion = GetVersionNum(data)
    # thisVersion = data[0].rstrip()
    # thisVersion = thisVersion[8:len(thisVersion)]

    if compareVersions(currentVersion, thisVersion):
        whiptailBox("msgbox", _("Update detected"),
                    _("An update has been detected for PiNet. Select OK to view the Release History."), False)
        displayChangeLog(currentVersion)
    else:
        print(_("No PiNet software updates found"))
        # print(thisVersion)
        # print(currentVersion)
        returnData(0)


def checkKernelFileUpdateWeb():
    # downloadFile(RawRepository +"/" + ReleaseBranch + "/boot/version.txt", "/tmp/kernelVersion.txt")
    downloadFile(RawBootRepository + "/" + ReleaseBranch + "/boot/version.txt", "/tmp/kernelVersion.txt")
    user = os.environ['SUDO_USER']
    currentPath = "/home/" + user + "/PiBoot/version.txt"
    if (os.path.isfile(currentPath)) == True:
        current = int(getCleanList(currentPath)[0])
        new = int(getCleanList("/tmp/kernelVersion.txt")[0])
        if new > current:
            returnData(1)
            return False
        else:
            returnData(0)
            print(_("No kernel updates found"))
            return True
    else:
        returnData(0)
        print(_("No kernel updates found"))


def checkKernelUpdater():
    downloadFile(RawRepository + "/" + ReleaseBranch + "/Scripts/kernelCheckUpdate.sh", "/tmp/kernelCheckUpdate.sh")

    if os.path.isfile("/opt/ltsp/armhf/etc/init.d/kernelCheckUpdate.sh"):

        currentVersion = int(getConfigParameter("/opt/ltsp/armhf/etc/init.d/kernelCheckUpdate.sh", "version=", True))
        newVersion = int(getConfigParameter("/tmp/kernelCheckUpdate.sh", "version=", True))
        if currentVersion < newVersion:
            installCheckKernelUpdater()
            returnData(1)
            return False
        else:
            returnData(0)
            return True
    else:
        installCheckKernelUpdater()
        returnData(1)
        return False


def installCheckKernelUpdater():
    shutil.copy("/tmp/kernelCheckUpdate.sh", "/opt/ltsp/armhf/etc/init.d/kernelCheckUpdate.sh")
    Popen(['ltsp-chroot', '--arch', 'armhf', 'chmod', '755', '/etc/init.d/kernelCheckUpdate.sh'], stdout=PIPE,
          stderr=PIPE, stdin=PIPE)
    process = Popen(['ltsp-chroot', '--arch', 'armhf', 'update-rc.d', 'kernelCheckUpdate.sh', 'defaults'], stdout=PIPE,
                    stderr=PIPE, stdin=PIPE)
    process.communicate()


# def importUsers():

def displayChangeLog(version):
    version = "Release " + version
    d = feedparser.parse(Repository + '/commits/' + ReleaseBranch + '.atom')
    releases = []
    for x in range(0, len(d.entries)):
        data = (d.entries[x].content[0].get('value'))
        data = ''.join(xml.etree.ElementTree.fromstring(data).itertext())
        data = data.split("\n")
        thisVersion = "Release " + GetVersionNum(data)
        # thisVersion = data[0].rstrip()
        if thisVersion == version:
            break
        elif x == 10:
            break
        if data[0][0:5] == "Merge":
            continue
        releases.append(data)
    output = []
    for i in range(0, len(releases)):
        output.append(releases[i][0])
        for z in range(0, len(releases[i])):
            if not z == 0:
                output.append(" - " + releases[i][z])
        output.append("")
    thing = ""
    for i in range(0, len(output)):
        thing = thing + output[i] + "\n"
    cmd = ["whiptail", "--title", _("Release history (Use arrow keys to scroll)") + " - " + version, "--scrolltext",
           "--" + "yesno", "--yes-button", _("Install ") + output[0], "--no-button", _("Cancel"), thing, "24", "78"]
    p = Popen(cmd, stderr=PIPE)
    out, err = p.communicate()
    if p.returncode == 0:
        updatePiNet()
        returnData(1)
        return True
    elif p.returncode == 1:
        returnData(0)
        return False
    else:
        return "ERROR"


def previousImport():
    items = ["passwd", "group", "shadow", "gshadow"]
    # items = ["group",]
    toAdd = []
    for x in range(0, len(items)):
        # migLoc = "/Users/Andrew/Documents/Code/pinetImportTest/" + items[x] + ".mig"
        # etcLoc = "/Users/Andrew/Documents/Code/pinetImportTest/" + items[x]
        migLoc = "/root/move/" + items[x] + ".mig"
        etcLoc = "/etc/" + items[x]
        debug("mig loc " + migLoc)
        debug("etc loc " + etcLoc)
        mig = getList(migLoc)
        etc = getList(etcLoc)
        for i in range(0, len(mig)):
            mig[i] = str(mig[i]).split(":")
        for i in range(0, len(etc)):
            etc[i] = str(etc[i]).split(":")
        for i in range(0, len(mig)):
            unFound = True
            for y in range(0, len(etc)):
                bob = mig[i][0]
                thing = etc[y][0]
                if bob == thing:
                    unFound = False
            if unFound:
                toAdd.append(mig[i])
        for i in range(0, len(toAdd)):
            etc.append(toAdd[i])
        for i in range(0, len(etc)):
            line = ""
            for y in range(0, len(etc[i])):
                line = line + etc[i][y] + ":"
            line = line[0:len(line) - 1]
            etc[i] = line
        debug(etc)
        writeTextFile(etc, etcLoc)


def openCSV(theFile):
    dataList = []
    if os.path.isfile(theFile):
        with open(theFile) as csvFile:
            data = csv.reader(csvFile, delimiter=' ', quotechar='|')
            for row in data:
                try:
                    theRow = str(row[0]).split(",")
                    dataList.append(theRow)
                except:
                    whiptailBox("msgbox", _("Error!"), _("CSV file invalid!"), False)
                    returnData("1")
                    sys.exit()
            return dataList

    else:
        print(_("Error! CSV file not found at") + " " + theFile)


def importUsersCSV(theFile, defaultPassword, dryRun=False):
    userDataList = []
    dataList = openCSV(theFile)
    if dryRun == "True" or dryRun == True:
        dryRun = True
    else:
        dryRun = False
    for userLine in dataList:
        user = userLine[0]
        if " " in user:
            whiptailBox("msgbox", _("Error!"),
                        _("CSV file names column (1st column) contains spaces in the usernames! This isn't supported."),
                        False)
            returnData("1")
            sys.exit()
        if len(userLine) >= 2:
            if userLine[1] == "":
                password = defaultPassword
            else:
                password = userLine[1]
        else:
            password = defaultPassword
        userDataList.append([user, password])
    allUserDataString = ""
    for i in range(0, len(userDataList)):
        allUserDataString = allUserDataString + _("Username") + " - " + userDataList[i][0] + " : " + _("Password - ") + \
                            userDataList[i][1] + "\n"
    cmd = ["whiptail", "--title", _("About to import (Use arrow keys to scroll)"), "--scrolltext", "--" + "yesno",
           "--yes-button", _("Import"), "--no-button", _("Cancel"), allUserDataString, "24", "78"]
    p = Popen(cmd, stderr=PIPE)
    out, err = p.communicate()
    if dryRun == False:
        if p.returncode == 0:
            for x in range(0, len(userDataList)):
                user = userDataList[x][0]
                password = userDataList[x][1]
                encPass = crypt.crypt(password, "22")
                cmd = ["useradd", "-m", "-s", "/bin/bash", "-p", encPass, user]
                p = Popen(cmd, stderr=PIPE)
                out, err = p.communicate()
                fixGroupSingle(user)
                percentComplete = int(((x + 1) / len(userDataList)) * 100)
                print(str(percentComplete) + "% - Import of " + user + " complete.")
            whiptailBox("msgbox", _("Complete"), _("Importing of CSV data has been complete."), False)
        else:
            sys.exit()


def usersCSVDelete(theFile, dryRun):
    userDataList = []
    dataList = openCSV(theFile)
    if dryRun == "True" or dryRun == True:
        dryRun = True
    else:
        dryRun = False
    for userLine in dataList:
        user = userLine[0]
        if " " in user:
            whiptailBox("msgbox", _("Error!"),
                        _("CSV file names column (1st column) contains spaces in the usernames! This isn't supported."),
                        False)
            returnData("1")
            sys.exit()
        userDataList.append([user, ])
    allUserDataString = ""
    for i in range(0, len(userDataList)):
        allUserDataString = allUserDataString + _("Username") + " - " + userDataList[i][0] + "\n"
    cmd = ["whiptail", "--title", _("About to attempt to delete (Use arrow keys to scroll)"), "--scrolltext",
           "--" + "yesno", "--yes-button", _("Delete"), "--no-button", _("Cancel"), allUserDataString, "24", "78"]
    p = Popen(cmd, stderr=PIPE)
    out, err = p.communicate()
    if dryRun == False:
        if p.returncode == 0:
            for x in range(0, len(userDataList)):
                user = userDataList[x][0]
                cmd = ["userdel", "-r", "-f", user]
                p = Popen(cmd, stderr=PIPE)
                out, err = p.communicate()
                percentComplete = int(((x + 1) / len(userDataList)) * 100)
                print(str(percentComplete) + "% - Delete of " + user + " complete.")
            whiptailBox("msgbox", _("Complete"), _("Delete of users from CSV file complete"), False)
        else:
            sys.exit()


def fixGroupSingle(username):
    groups = ["adm", "dialout", "cdrom", "audio", "users", "video", "games", "plugdev", "input", "pupil"]
    for x in range(0, len(groups)):
        cmd = ["usermod", "-a", "-G", groups[x], username]
        p = Popen(cmd, stderr=PIPE)
        out, err = p.communicate()


def checkIfFileContains(file, string):
    """
    Simple function to check if a string exists in a file.
    """

    textfile = getList(file)
    unfound = True
    for i in range(0, len(textfile)):
        found = textfile[i].find(string)
        # print("Searching line number " + str(i) + ". Found status is " + str(found))
        # print(textfile[i])
        # print("")
        if (found != -1):
            unfound = False

    if unfound:
        returnData(0)
    else:
        returnData(1)


def savePickled(toSave, path="/tmp/pinetSoftware.dump"):
    """
    Saves list of softwarePackage objects.
    """
    with open(path, "wb") as output:
        pickle.dump(toSave, output, pickle.HIGHEST_PROTOCOL)


def loadPickled(path="/tmp/pinetSoftware.dump", deleteAfter=True):
    """
    Loads list of softwarePackage objects ready to be used.
    """
    try:
        with open(path, "rb") as input:
            obj = pickle.load(input)
        if deleteAfter:
            removeFile(path)
        return obj
    except (OSError, IOError):
        if deleteAfter:
            removeFile(path)
        return []


def installEpoptes():
    """
    Install Epoptes classroom management software. Key is making sure groups are correct.
    :return:
    """
    softwarePackage("epoptes", "apt", installOnServer=True).installPackage()
    runBash("gpasswd -a root staff")
    softwarePackage("epoptes-client", "apt", parameters=("--no-install-recommends",)).installPackage()
    ltspChroot("epoptes-client -c")
    replaceLineOrAdd("/etc/default/epoptes", "SOCKET_GROUP", "SOCKET_GROUP=teacher")

    # Todo - Remove later if happy has been replaced by above.
    # runBash("apt-get install -y epoptes")
    # runBash("gpasswd -a root staff")
    # runBash("ltsp-chroot --arch armhf apt-get install -y epoptes-client --no-install-recommends")
    # runBash("ltsp-chroot --arch armhf epoptes-client -c")


def installScratchGPIO():
    """
    ScratchGPIO installation process. Includes creating the desktop icon in all users and /etc/skel
    """
    removeFile("/tmp/isgh7.sh")
    removeFile("/opt/ltsp/armhf/usr/local/bin/isgh5.sh")
    removeFile("/opt/ltsp/armhf/usr/local/bin/scratchSudo.sh")
    removeFile("/opt/ltsp/armhf/usr/local/bin/isgh7.sh")
    downloadFile("http://bit.ly/1wxrqdp", "/tmp/isgh7.sh")
    copyFileFolder("/tmp/isgh7.sh", "/opt/ltsp/armhf/usr/local/bin/isgh7.sh")
    replaceLineOrAdd("/opt/ltsp/armhf/usr/local/bin/scratchSudo.sh", "bash /usr/local/bin/isgh7.sh $SUDO_USER",
                     "bash /usr/local/bin/isgh7.sh $SUDO_USER")
    users = getUsers()
    for u in users:
        createTextFile("/home/" + u + "/Desktop/Install-scratchGPIO.desktop", """
        [Desktop Entry]
        Version=1.0
        Name=Install ScratchGPIO
        Comment=Install ScratchGPIO
        Exec=sudo bash /usr/local/bin/scratchSudo.sh
        Icon=scratch
        Terminal=true
        Type=Application
        Categories=Utility;Application;
        """)
        os.chown("/home/" + u + "/Desktop/Install-scratchGPIO.desktop", pwd.getpwnam(u).pw_uid, grp.getgrnam(u).gr_gid)
    makeFolder("/etc/skel/Desktop")
    createTextFile("/etc/skel/Desktop/Install-scratchGPIO.desktop",
                   """[Desktop Entry]
    Version=1.0
    Name=Install ScratchGPIO
    Comment=Install ScratchGPIO
    Exec=sudo bash /usr/local/bin/scratchSudo.sh
    Icon=scratch
    Terminal=true
    Type=Application
    Categories=Utility;Application;""")


def installSoftwareList(holdOffInstall=False):
    """
    Replacement for ExtraSoftware function in bash.
    Builds a list of possible software to install (using softwarePackage class) then displays the list using checkbox Whiptail menu.
    Checks what options the user has collected, then saves the packages list to file (using pickle). If holdOffInstall is False, then runs installSoftwareFromFile().
    """
    software = []

    software.append(
        softwarePackage("Arduino-IDE", "apt", description=_("Programming environment for Arduino microcontrollers"),
                        installCommands=["arduino", ]))
    software.append(
        softwarePackage("Scratch-gpio", "scratchGPIO", description=_("A special version of scratch for GPIO work")))
    software.append(
        softwarePackage("Epoptes", "epoptes", description=_("Free and open source classroom management software")))
    software.append(softwarePackage("Custom-package", "customApt",
                                    description=_(
                                        "Allows you to enter the name of a package from Raspbian repository")))
    software.append(
        softwarePackage("Custom-python", "customPip",
                        description=_("Allows you to enter the name of a Python library from pip.")))

    softwareList = []
    for i in software:
        softwareList.append([i.name, i.description])
    done = False
    if (shutil.get_terminal_size()[0] < 105) or (shutil.get_terminal_size()[0] < 30):
        print("\x1b[8;30;105t")
        time.sleep(0.05)
        # print("Resizing")
    while done == False:
        whiptailBox("msgbox", _("Additional Software"), _(
            "In the next window you can select additional software you wish to install. Use space bar to select applications and hit enter when you are finished."),
                    False)
        result = (whiptailCheckList(_("Extra Software Submenu"), _(
            "Select any software you want to install. Use space bar to select then enter to continue."), softwareList))
        try:
            result = result.decode("utf-8")
        except AttributeError:
            return
        result = result.replace('"', '')
        if result != "Cancel":
            if result == "":
                yesno = whiptailBox("yesno", _("Are you sure?"),
                                    _("Are you sure you don't want to install any additional software?"), True)
                if yesno:
                    savePickled(software)
                    done = True
            else:
                resultList = result.split(" ")
                yesno = whiptailBox("yesno", _("Are you sure?"),
                                    _("Are you sure you want to install this software?") + " \n" + (
                                        result.replace(" ", "\n")), True, height=str(7 + len(result.split(" "))))
                if yesno:
                    for i in software:
                        if i.name in resultList:
                            i.customAptPip()
                            # i.marked = True
                    done = True
                    savePickled(software)

    if holdOffInstall == False:
        installSoftwareFromFile()


def installSoftwareFromFile(packages=None):
    """
    Second part of installSoftwareList().
    Loads the pickle encoded list of softwarePackage objects then if they are marked to be installed, installs then.
    """
    needCompress = False
    if packages == None:
        packages = loadPickled()
    for i in packages:
        if i.marked == True:
            print(_("Installing") + " " + str(i.name))
            if needCompress == False:
                ltspChroot("apt-get update")
            i.installPackage()
            i.marked = False
            setConfigParameter("NBDBuildNeeded", "true")
            needCompress = True
        else:
            debug("Not installing " + str(i.name))
    if needCompress:
        nbdRun()


def installChrootSoftware():
    packages = ['idle', 'idle3', 'python-dev', 'nano', 'python3-dev', 'scratch', 'python3-tk', 'git',
                'debian-reference-en',
                'dillo', 'python', 'python-pygame', 'python3-pygame', 'python-tk', 'sudo', 'sshpass', 'pcmanfm',
                'python3-numpy',
                'wget', 'xpdf', 'gtk2-engines', 'alsa-utils', 'wpagui', 'omxplayer', 'lxde', 'net-tools', 'mpg123',
                'ssh',
                'locales', 'less', 'fbset', 'sudo', 'psmisc', 'strace', 'module-init-tools', 'ifplugd', 'ed', 'ncdu',
                'console-setup', 'keyboard-configuration', 'debconf-utils', 'parted', 'unzip', 'build-essential',
                'manpages-dev',
                'python', 'bash-completion', 'gdb', 'pkg-config', 'python-rpi.gpio', 'v4l-utils', 'lua5.1', 'luajit',
                'hardlink',
                'ca-certificates', 'curl', 'fake-hwclock', 'ntp', 'nfs-common', 'usbutils', 'libraspberrypi-dev',
                'libraspberrypi-doc', 'libfreetype6-dev', 'python3-rpi.gpio', 'python-rpi.gpio', 'python-pip',
                'python3-pip',
                'python-picamera', 'python3-picamera', 'x2x', 'wolfram-engine', 'xserver-xorg-video-fbturbo',
                'netsurf-common',
                'netsurf-gtk', 'rpi-update', 'ftp', 'libraspberrypi-bin', 'python3-pifacecommon',
                'python3-pifacedigitalio',
                'python3-pifacedigital-scratch-handler', 'python-pifacecommon', 'python-pifacedigitalio', 'i2c-tools',
                'man-db',
                'minecraft-pi', 'python-smbus', 'python3-smbus', 'dosfstools', 'ruby', 'iputils-ping', 'scrot',
                'gstreamer1.0-x',
                'gstreamer1.0-omx', 'gstreamer1.0-plugins-base', 'gstreamer1.0-plugins-good',
                'gstreamer1.0-plugins-bad',
                'gstreamer1.0-alsa', 'gstreamer1.0-libav', 'java-common', 'oracle-java8-jdk', 'apt-utils',
                'wpasupplicant',
                'wireless-tools', 'firmware-atheros', 'firmware-brcm80211', 'firmware-libertas', 'firmware-ralink',
                'firmware-realtek', 'libpng12-dev', 'linux-image-3.18.0-trunk-rpi', 'linux-image-3.18.0-trunk-rpi2',
                'linux-image-3.12-1-rpi', 'linux-image-3.10-3-rpi', 'linux-image-3.2.0-4-rpi', 'linux-image-rpi-rpfv',
                'linux-image-rpi2-rpfv', 'chromium', 'smartsim', 'penguinspuzzle', 'alacarte', 'rc-gui', 'claws-mail',
                'tree',
                'greenfoot', 'bluej', 'raspi-gpio', 'libreoffice', 'nuscratch', 'iceweasel', 'mu']

    packages.append(softwarePackage("idle", "apt"))
    packages.append(softwarePackage("idle3", "apt"))
    packages.append(softwarePackage("python-dev", "apt"))
    packages.append(softwarePackage("nano", "apt"))
    packages.append(softwarePackage("python3-dev", "apt"))
    packages.append(softwarePackage("scratch", "apt"))
    packages.append(softwarePackage("python3-tk", "apt"))
    packages.append(softwarePackage("git", "apt"))
    packages.append(softwarePackage("debian-reference-en", "apt"))
    packages.append(softwarePackage("dillo", "apt"))
    packages.append(softwarePackage("python", "apt"))
    packages.append(softwarePackage("python-pygame", "apt"))
    packages.append(softwarePackage("python3-pygame", "apt"))
    packages.append(softwarePackage("python-tk", "apt"))
    packages.append(softwarePackage("sudo", "apt"))
    packages.append(softwarePackage("sshpass", "apt"))
    packages.append(softwarePackage("pcmanfm", "apt"))
    packages.append(softwarePackage("python3-numpy", "apt"))
    packages.append(softwarePackage("wget", "apt"))
    packages.append(softwarePackage("xpdf", "apt"))
    packages.append(softwarePackage("gtk2-engines", "apt"))
    packages.append(softwarePackage("alsa-utils", "apt"))
    packages.append(softwarePackage("wpagui", "apt"))
    packages.append(softwarePackage("omxplayer", "apt"))
    packages.append(softwarePackage("lxde", "apt"))
    packages.append(softwarePackage("net-tools", "apt"))
    packages.append(softwarePackage("mpg123", "apt"))
    packages.append(softwarePackage("ssh", "apt"))
    packages.append(softwarePackage("locales", "apt"))
    packages.append(softwarePackage("less", "apt"))
    packages.append(softwarePackage("fbset", "apt"))
    packages.append(softwarePackage("sudo", "apt"))
    packages.append(softwarePackage("psmisc", "apt"))
    packages.append(softwarePackage("strace", "apt"))
    packages.append(softwarePackage("module-init-tools", "apt"))
    packages.append(softwarePackage("ifplugd", "apt"))
    packages.append(softwarePackage("ed", "apt"))
    packages.append(softwarePackage("ncdu", "apt"))
    packages.append(softwarePackage("console-setup", "apt"))
    packages.append(softwarePackage("keyboard-configuration", "apt"))
    packages.append(softwarePackage("debconf-utils", "apt"))
    packages.append(softwarePackage("parted", "apt"))
    packages.append(softwarePackage("unzip", "apt"))
    packages.append(softwarePackage("build-essential", "apt"))
    packages.append(softwarePackage("manpages-dev", "apt"))
    packages.append(softwarePackage("python", "apt"))
    packages.append(softwarePackage("bash-completion", "apt"))
    packages.append(softwarePackage("gdb", "apt"))
    packages.append(softwarePackage("pkg-config", "apt"))
    packages.append(softwarePackage("python-rpi.gpio", "apt"))
    packages.append(softwarePackage("v4l-utils", "apt"))
    packages.append(softwarePackage("lua5.1", "apt"))
    packages.append(softwarePackage("luajit", "apt"))
    packages.append(softwarePackage("hardlink", "apt"))
    packages.append(softwarePackage("ca-certificates", "apt"))
    packages.append(softwarePackage("curl", "apt"))
    packages.append(softwarePackage("fake-hwclock", "apt"))
    packages.append(softwarePackage("ntp", "apt"))
    packages.append(softwarePackage("nfs-common", "apt"))
    packages.append(softwarePackage("usbutils", "apt"))
    packages.append(softwarePackage("libraspberrypi-dev", "apt"))
    packages.append(softwarePackage("libraspberrypi-doc", "apt"))
    packages.append(softwarePackage("libfreetype6-dev", "apt"))
    packages.append(softwarePackage("python3-rpi.gpio", "apt"))
    packages.append(softwarePackage("python-rpi.gpio", "apt"))
    packages.append(softwarePackage("python-pip", "apt"))
    packages.append(softwarePackage("python3-pip", "apt"))
    packages.append(softwarePackage("python-picamera", "apt"))
    packages.append(softwarePackage("python3-picamera", "apt"))
    packages.append(softwarePackage("x2x", "apt"))
    packages.append(softwarePackage("wolfram-engine", "apt"))
    packages.append(softwarePackage("xserver-xorg-video-fbturbo", "apt"))
    packages.append(softwarePackage("netsurf-common", "apt"))
    packages.append(softwarePackage("netsurf-gtk", "apt"))
    packages.append(softwarePackage("rpi-update", "apt"))
    packages.append(softwarePackage("ftp", "apt"))
    packages.append(softwarePackage("libraspberrypi-bin", "apt"))
    packages.append(softwarePackage("python3-pifacecommon", "apt"))
    packages.append(softwarePackage("python3-pifacedigitalio", "apt"))
    packages.append(softwarePackage("python3-pifacedigital-scratch-handler", "apt"))
    packages.append(softwarePackage("python-pifacecommon", "apt"))
    packages.append(softwarePackage("python-pifacedigitalio", "apt"))
    packages.append(softwarePackage("i2c-tools", "apt"))
    packages.append(softwarePackage("man-db", "apt"))
    packages.append(softwarePackage("minecraft-pi", "apt"))
    packages.append(softwarePackage("python-smbus", "apt"))
    packages.append(softwarePackage("python3-smbus", "apt"))
    packages.append(softwarePackage("dosfstools", "apt"))
    packages.append(softwarePackage("ruby", "apt"))
    packages.append(softwarePackage("iputils-ping", "apt"))
    packages.append(softwarePackage("scrot", "apt"))
    packages.append(softwarePackage("gstreamer1.0-x", "apt"))
    packages.append(softwarePackage("gstreamer1.0-omx", "apt"))
    packages.append(softwarePackage("gstreamer1.0-plugins-base", "apt"))
    packages.append(softwarePackage("gstreamer1.0-plugins-good", "apt"))
    packages.append(softwarePackage("gstreamer1.0-plugins-bad", "apt"))
    packages.append(softwarePackage("gstreamer1.0-alsa", "apt"))
    packages.append(softwarePackage("gstreamer1.0-libav", "apt"))
    packages.append(softwarePackage("java-common", "apt"))
    packages.append(softwarePackage("oracle-java8-jdk", "apt"))
    packages.append(softwarePackage("apt-utils", "apt"))
    packages.append(softwarePackage("wpasupplicant", "apt"))
    packages.append(softwarePackage("wireless-tools", "apt"))
    packages.append(softwarePackage("firmware-atheros", "apt"))
    packages.append(softwarePackage("firmware-brcm80211", "apt"))
    packages.append(softwarePackage("firmware-libertas", "apt"))
    packages.append(softwarePackage("firmware-ralink", "apt"))
    packages.append(softwarePackage("firmware-realtek", "apt"))
    packages.append(softwarePackage("libpng12-dev", "apt"))
    packages.append(softwarePackage("linux-image-3.18.0-trunk-rpi", "apt"))
    packages.append(softwarePackage("linux-image-3.18.0-trunk-rpi2", "apt"))
    packages.append(softwarePackage("linux-image-3.12-1-rpi", "apt"))
    packages.append(softwarePackage("linux-image-3.10-3-rpi", "apt"))
    packages.append(softwarePackage("linux-image-3.2.0-4-rpi", "apt"))
    packages.append(softwarePackage("linux-image-rpi-rpfv", "apt"))
    packages.append(softwarePackage("linux-image-rpi2-rpfv", "apt"))
    packages.append(softwarePackage("chromium", "apt"))
    packages.append(softwarePackage("smartsim", "apt"))
    packages.append(softwarePackage("penguinspuzzle", "apt"))
    packages.append(softwarePackage("alacarte", "apt"))
    packages.append(softwarePackage("rc-gui", "apt"))
    packages.append(softwarePackage("claws-mail", "apt"))
    packages.append(softwarePackage("tree", "apt"))
    packages.append(softwarePackage("greenfoot", "apt"))
    packages.append(softwarePackage("bluej", "apt"))
    packages.append(softwarePackage("raspi-gpio", "apt"))
    packages.append(softwarePackage("libreoffice", "apt"))
    packages.append(softwarePackage("nuscratch", "apt"))
    packages.append(softwarePackage("iceweasel", "apt"))
    packages.append(softwarePackage("mu", "apt"))


def nbdRun():
    """
    Runs NBD compression tool. Clone of version in main pinet script
    """
    if getConfigParameter("/etc/pinet", "NBD=") == "true":
        if getConfigParameter("/etc/pinet", "NBDuse=") == "true":
            print("--------------------------------------------------------")
            print(_("Compressing the image, this will take roughly 5 minutes"))
            print("--------------------------------------------------------")
            runBash("ltsp-update-image /opt/ltsp/armhf")
            setConfigParameter("NBDBuildNeeded", "false")
        else:
            whiptailBox("msgbox", _("WARNING"), _(
                "Auto NBD compressing is disabled, for your changes to push to the Raspberry Pis, run NBD-recompress from main menu."),
                        False)


def generateServerID():
    """
    Generates random server ID for use with stats system.
    """
    ID = random.randint(10000000000, 99999999999)
    setConfigParameter("ServerID", str(ID))


def getIPAddress():
    """
    Get the PiNet server external IP address using the dnsdynamic.org IP address checker.
    If there is any issues, defaults to returning 0.0.0.0.
    """
    try:
        with urllib.request.urlopen("http://myip.dnsdynamic.org/") as url:
            IP = url.read().decode()
            socket.inet_aton(IP)
    except:
        IP = "0.0.0.0"
    return IP


def sendStats():
    """
    Upload anonymous stats to the secure PiNet server (over encrypted SSL).
    """
    DisableMetrics = str(getConfigParameter("/etc/pinet", "DisableMetrics="))
    ServerID = str(getConfigParameter("/etc/pinet", "ServerID="))
    if ServerID == "None":
        generateServerID()
        ServerID = str(getConfigParameter("/etc/pinet", "ServerID="))
    if DisableMetrics.lower() == "true":
        PiNetVersion = "0.0.0"
        Users = "0"
        KernelVersion = "000"
        ReleaseChannel = "0"
        City = "Blank"
        OrganisationType = "Blank"
        OrganisationName = "Blank"
    else:
        PiNetVersion = str(getConfigParameter("/usr/local/bin/pinet", "version=", True))
        Users = str(len(getUsers()))
        if os.path.exists("/home/" + os.environ['SUDO_USER'] + "/PiBoot/version.txt"):
            KernelVersion = str(getCleanList("/home/" + os.environ['SUDO_USER'] + "/PiBoot/version.txt")[0])
        else:
            KernelVersion = "000"
        City = str(getConfigParameter("/etc/pinet", "City="))
        OrganisationType = str(getConfigParameter("/etc/pinet", "OrganisationType="))
        OrganisationName = str(getConfigParameter("/etc/pinet", "OrganisationName="))
        ReleaseChannel = str(getConfigParameter("/etc/pinet", "ReleaseChannel="))

    IPAddress = getIPAddress()

    command = 'curl --connect-timeout 2 --data "ServerID=' + ServerID + "&" + "PiNetVersion=" + PiNetVersion + "&" + "Users=" + Users + "&" + "KernelVersion=" + KernelVersion + "&" + "ReleaseChannel=" + ReleaseChannel + "&" + "IPAddress=" + IPAddress + "&" + "City=" + City + "&" + "OrganisationType=" + OrganisationType + "&" + "OrganisationName=" + OrganisationName + '"  https://secure.pinet.org.uk/pinetstatsv1.php -s -o /dev/null 2>&1'
    runBash(command, ignoreErrors=True)


def checkStatsNotification():
    """
    Displays a one time notification to the user only once on the metrics.
    """
    ShownStatsNotification = str(getConfigParameter("/etc/pinet", "ShownStatsNotification="))
    if ShownStatsNotification == "true":
        pass  # Don't display anything
    else:
        whiptailBox("msgbox", _("Stats"), _(
            "Please be aware PiNet now collects very basic usage stats. These stats are uploaded to the secure PiNet metrics server over an encrypted 2048 bit SSL/TLS connection. The stats logged are PiNet version, Raspbian kernel version, number of users, development channel (stable or dev), external IP address, a randomly generated unique ID and any additional information you choose to add. These stats are uploaded in the background when PiNet checks for updates. Should you wish to disable the stats, see - http://pinet.org.uk/articles/advanced/metrics.html"),
                    False, height="14")
        setConfigParameter("ShownStatsNotification", "true", "/etc/pinet")
        askExtraStatsInfo()


def askExtraStatsInfo():
    """
    Ask the user for additional stats information.
    """
    whiptailBox("msgbox", _("Additional information"), _(
        "It is really awesome to see and hear from users across the world using PiNet. So we can start plotting schools/organisations using PiNet on a map, feel free to add any extra information to your PiNet server. It hugely helps us out also for internationalisation/localisation of PiNet. If you do not want to attach any extra information, please simply leave the following prompts blank."),
                False, height="13")
    city = whiptailBox("inputbox", _("Nearest major city"), _(
        "To help with putting a dot on the map for your server, what is your nearest major town or city? Leave blank if you don't want to answer."),
                       False, returnErr=True)
    organisationType = whiptailSelectMenu(_("Organisation type"), _(
        "What type of organisation are you setting PiNet up for? Leave on blank if you don't want to answer."),
                                          ["Blank", "School", "Non Commercial Organisation", "Commercial Organisation",
                                           "Raspberry Jam/Club", "N/A"])
    organisationName = whiptailBox("inputbox", _("School/organisation name"),
                                   _("What is the name of your organisation? Leave blank if you don't want to answer."),
                                   False, returnErr=True)
    whiptailBox("msgbox", _("Additional information"), _(
        'Thanks for taking the time to read through (and if possible fill in) additional information. If you ever want to edit your information supplied, you can do so by selecting the "Other" menu and selecting "Edit-Information".'),
                False, height="11")
    try:
        organisationType = organisationType.decode("utf-8")
    except:
        organisationType = "Blank"
    if city == "":
        city = "Blank"
    if organisationType == "":
        organisationType = "Blank"
    if organisationName == "":
        organisationName = "Blank"
    city = re.sub('[^0-9a-zA-Z]+', '_', city)
    organisationType = re.sub('[^0-9a-zA-Z]+', '_', organisationType)
    organisationName = re.sub('[^0-9a-zA-Z]+', '_', organisationName)
    setConfigParameter("City", city)
    setConfigParameter("OrganisationType", organisationType)
    setConfigParameter("OrganisationName", organisationName)
    sendStats()


def decodeBashOutput(inputData, decode=False, removen=False):
    if decode:
        try:
            inputData = inputData.decode("utf-8")
        except:
            pass
    if removen:
        inputData = inputData.rstrip('\n')

    return inputData


def backupChroot(name=None, override=False):
    makeFolder("/opt/PiNet/chrootBackups")
    chrootSize = int(
        decodeBashOutput(runBash("""sudo du -s /opt/ltsp/armhf | awk '{print $1}' """, returnString=True), decode=True,
                         removen=True))
    remainingSpace = int(
        decodeBashOutput(runBash("""sudo df | grep /dev/ | sed -n 1p | awk '{print $4}' """, returnString=True),
                         decode=True,
                         removen=True))
    if ((remainingSpace - chrootSize) > 1000000) or override:
        waitingForName = True
        if name == None:
            waitingForName = True
            while waitingForName:
                name = whiptailBox("inputbox", _("Backup Chroot name"),
                                   _("Please enter a name to store the backup chroot under. Do not include spaces."),
                                   False, returnErr=True)
                if (' ' in name) or (name == ""):
                    whiptailBox("msgbox", _("Invalid name"),
                                _("Please do not include spaces in the filename or leave the filename blank."), False)
                else:
                    waitingForName = False
                    # print("Starting copy. This may take up to 10 minutes.")
        try:
            # for i in os.listdir("/opt/ltsp/armhf"):
            #    if (not i == "proc") and (not i == "dev"):
            #        print("Copying " + "/opt/ltsp/armhf/" + i)
            #        #makeFolder("/opt/PiNet/chrootBackups/" + backupName + "/" + i)
            #        copyFileFolder("/opt/ltsp/armhf/" + i, "/opt/PiNet/chrootBackups/" + backupName + "/" + i)
            print("-------------------------------------------------------------")
            print("Backing up Raspbian Chroot... This may take up to 20 minutes.")
            print("-------------------------------------------------------------")
            runBash("sudo cp -rp /opt/ltsp/armhf/ /opt/PiNet/chrootBackups/" + name)
            print("Copy complete.")
            whiptailBox("msgbox", _("Backup complete"), _("Backup has been complete"), False)
            return True
        except:
            print("Backup failed!")
            whiptailBox("msgbox", _("Error!"), _("Backup failed!"), False)
            return False
    else:
        print("Space issue...")
        chrootSizeReadable = int(
            decodeBashOutput(runBash("""sudo du -s /opt/ltsp/armhf | awk '{print $1}' """, returnString=True),
                             decode=True,
                             removen=True))
        remainingSpacechrootSizeReadable = int(
            decodeBashOutput(runBash("""sudo df | grep /dev/ | sed -n 1p | awk '{print $4}' """, returnString=True),
                             decode=True,
                             removen=True))
        print(remainingSpacechrootSizeReadable, chrootSizeReadable)
        override = whiptailBoxYesNo("Not enough space",
                                    "PiNet has detected not enough space is left to store the backup. " + str(
                                        chrootSizeReadable) + " is required, but only " + str(
                                        remainingSpacechrootSizeReadable) + " is available. You can choose to override this check.",
                                    customYes="Override", customNo="Cancel", returnTrueFalse=True, height="11")
        if override:
            backupChroot(name, True)
            return True
        return False


def restoreChroot():
    options = []
    for i in os.listdir("/opt/PiNet/chrootBackups/"):
        options.append(i)
    if len(options) == 0:
        whiptailBox("msgbox", _("No backups"), _("No Raspbian chroots found "), False)
    else:
        name = decodeBashOutput(
            whiptailSelectMenu(_("Select backup"), _("Select your Raspbian chroot backup to restore"), options), True,
            False)
        if os.path.isdir("/opt/PiNet/chrootBackups/" + name) and name != "" and name != None and os.path.isdir(
                                "/opt/PiNet/chrootBackups/" + name + "/boot"):
            answer = whiptailBox("yesno", _("Are you sure?"), _(
                "The old Raspbian chroot will now be deleted and your chosen one copied into its place. There is no way to undo this process. Are you sure you wish to proceed?"),
                                 True, height="9")
            if answer:
                runBash("rm -rf /opt/ltsp/armhf")
                print("Starting restore...")
                runBash("cp -rp /opt/PiNet/chrootBackups/" + name + " /opt/ltsp/armhf")
                print("Restore complete")
                nbdRun()
        else:
            whiptailBox("msgbox", _("Unable to restore"), _(
                "Unable to restore backup chroot. The Raspbian chroot being restored is corrupt or damaged. Your previous Rabpain chroot has been left untouched."),
                        False)


def checkDebianVersion():
    wheezy = checkStringExists("/opt/ltsp/armhf/etc/apt/sources.list",
                               "deb http://mirrordirector.raspbian.org/raspbian/ wheezy")
    if wheezy == True:
        debianWheezyToJessieUpdate()
    else:
        returnData(0)


def debianWheezyToJessieUpdate(tryBackup=True):
    whiptailBox("msgbox", _("Raspbian Jessie update"), _(
        "A major update for your version of Raspbian is available. You are currently running Raspbian Wheezy, although the next big release (Raspbian Jessie) has now been released by the Raspberry Pi Foundation. As they have officially discontinued support for Raspbian Wheezy, it is highly recommended you proceed with the automatic update. Note that any custom configurations or changes you have made with Raspbian will be reset on installation of this update. Future updates for PiNet will only support Raspbian Jessie."),
                False, height="14")
    yesno = whiptailBox("yesno", _("Proceed"), _(
        "Would you like to proceed with Raspbian Jessie update? It will take 1-2 hours as Raspbian will be fully rebuilt. Note PiNet Wheezy support will be officially discontinued on 1st July 2016."),
                        True)
    if yesno and internetFullStatusCheck():
        backupName = "RaspbianWheezyBackup" + str(time.strftime("-%d-%m-%Y"))
        whiptailBox("msgbox", _("Backup chroot"), _(
            "Before proceeding with the update, a backup of the Raspbian chroot will be performed. You can revert to this later if need be. It will be called " + backupName),
                    False, height="10")
        if backupChroot(backupName):
            returnData(1)
            return

    returnData(0)


# ------------------------------Main program-------------------------

getReleaseChannel()
setupLogger()

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(_("This python script does nothing on its own, it must be passed stuff"))
    else:
        if sys.argv[1] == "replaceLineOrAdd":
            replaceLineOrAdd(sys.argv[2], sys.argv[3], sys.argv[4])
        elif sys.argv[1] == "replaceBitOrAdd":
            replaceBitOrAdd(sys.argv[2], sys.argv[3], sys.argv[4])
        elif sys.argv[1] == "CheckInternet":
            internet_on(sys.argv[2])
        elif sys.argv[1] == "CheckUpdate":
            checkUpdate(sys.argv[2])
        elif sys.argv[1] == "CompareVersion":
            compareVersions(sys.argv[2], sys.argv[3])
        elif sys.argv[1] == "updatePiNet":
            updatePiNet()
        elif sys.argv[1] == "triggerInstall":
            downloadFile("http://bit.ly/pinetinstall1", "/dev/null")
        elif sys.argv[1] == "checkKernelFileUpdateWeb":
            checkKernelFileUpdateWeb()
        elif sys.argv[1] == "checkKernelUpdater":
            checkKernelUpdater()
        elif sys.argv[1] == "installCheckKernelUpdater":
            installCheckKernelUpdater()
        elif sys.argv[1] == "previousImport":
            previousImport()
        elif sys.argv[1] == "importFromCSV":
            importUsersCSV(sys.argv[2], sys.argv[3])
        elif sys.argv[1] == "usersCSVDelete":
            usersCSVDelete(sys.argv[2], sys.argv[3])
        elif sys.argv[1] == "checkIfFileContainsString":
            checkIfFileContains(sys.argv[2], sys.argv[3])
        elif sys.argv[1] == "initialInstallSoftwareList":
            installSoftwareList(True)
        elif sys.argv[1] == "installSoftwareList":
            installSoftwareList(False)
        elif sys.argv[1] == "installSoftwareFromFile":
            installSoftwareFromFile()
        elif sys.argv[1] == "sendStats":
            sendStats()
        elif sys.argv[1] == "checkStatsNotification":
            checkStatsNotification()
        elif sys.argv[1] == "askExtraStatsInfo":
            askExtraStatsInfo()
        elif sys.argv[1] == "internetFullStatusCheck":
            internetFullStatusCheck()
        elif sys.argv[1] == "checkDebianVersion":
            checkDebianVersion()
        elif sys.argv[1] == "setConfigParameter":
            setConfigParameter(sys.argv[2], sys.argv[3])