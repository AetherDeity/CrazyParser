#!/usr/bin/python
'''

This script uses urlcrazy and dnstwist to identify possible typosquatted
domains. The output is compared against an existing list of typosquatted
domains generated by an initial review. If any new domains are identified,
the results are mailed off for review and blocking in your web proxy.

    Dependencies:
        mydomains.csv
            This file contains a list of domains you wish to monitor. 

        knowndomains.csv
            This file contains domains already identified from previous
            runs. The file contains a header "Domain,Reason" and a list of
            domains, 1 per line. The reason will either be Squatter or
            Valid Site if the domain belongs to a legitimate site.

	urlcrazy: installed at /usr/bin/urlcrazy. If this installed in an
            alternate location, the value of urlcrazyPath will need to be
            updated to reflect its location.

	dnstwist: installed at /opt/dnstwist/dnstwist.py. If this installed in an
            alternate location, the value of dnstwistPath will need to be
            updated to reflect its location.

crazyParser.py - by @hardwaterhacker - http://hardwatersec.blogspot.com
mike@hardwatersecurity.com
'''

__author__ = 'Mike Saunders'
__version__ = '20150930'
__email__ = 'mike@hardwatersecurity.com'

import argparse
import os
import sys
import subprocess
import csv
import smtplib
from tempfile import TemporaryFile
from email.MIMEMultipart import MIMEMultipart
from email.MIMEBase import MIMEBase
from email.MIMEText import MIMEText
from email import Encoders
import atexit

urlcrazyPath = '/usr/bin/urlcrazy' # update if your installation differs
dnstwistPath = '/opt/dnstwist/dnstwist.py' # update if your installation differs


# set up global defaults
tempFiles = [] # define temporary files array

def checkPerms(docRoot, resultsFile):
    # Test if we have execute permissions to docRoot
    if not os.access(docRoot, os.X_OK):
        print "Destination directory " + docRoot + " not accessible."
        print "Please check permissions.  Exiting..."
        sys.exit()
    else:
        pass

    # Test if we have write permissions to docRoot
    try:
        permtest = TemporaryFile('w+b', bufsize=-1, dir=docRoot)
    except OSError:
        print "Unable to write to desired directory: " + docRoot + "."
        print "Please check permissions.  Exiting..."
        sys.exit()

def checkDepends(myDomains, knownDomains, urlcrazy, dnstwist):
    # Test if mydomains.csv exists
    if not os.access(myDomains, os.F_OK) or not os.access(knownDomains, os.F_OK):
        print "Required configuration files - mydomains.csv or knowndomains.csv - not found."
        print "Please verify configuration."
        sys.exit()
    else:
        pass

    # Test if urlcrazy exists
    if urlcrazy:
        if not os.access(urlcrazyPath, os.F_OK):
            print "URLCrazy specified as " + urlcrazyPath + " but was not found."
            print "Please check urlcrazyPath in crazyParser.py.  Exiting..."
            sys.exit()

    # Test if dnstwist exists
    if dnstwist:
        if not os.access(dnstwistPath, os.F_OK):
            print "DNStwist specified as " + dnstwistPath + "but was not found."
            print "Please check urlcrazyPath in crazyParser.py.  Exiting..."
            sys.exit()
                 
def doCrazy(docRoot, resultsFile, myDomains, urlcrazy, dnstwist):
    # cleanup old results file
    try:
        os.remove(resultsFile)
    except OSError:
        pass
    
    with open(myDomains, 'rbU') as domains:
        reader = csv.reader(domains)
        for domain in domains:
            ucoutfile = os.path.join(docRoot,(domain.rstrip() + '.uctmp'))
            dtoutfile = os.path.join(docRoot,(domain.rstrip() + '.dttmp'))
            domain = domain.rstrip()
                
            # Run urlcrazy if enabled
            ucargs=[urlcrazyPath, '-f', 'csv', '-o', ucoutfile, domain]
            if urlcrazy:
                try:
                    with open(os.devnull, 'w') as devnull:
                        subprocess.call(ucargs, stdout=devnull, close_fds=True, shell=False)
                        tempFiles.append(ucoutfile)
                except:
                    # An error occurred running urlcrazy
                    ## Need to test if uelcrazy exists.  If not, raise exception.
                    print "Unexpected error running urlcrazy:", sys.exc_info()[0]
                    pass

            # Run dnstwist if enabled
            dtargs=[dnstwistPath, '-r', '-c', domain]
            if dnstwist:
                try:
                    with open(dtoutfile, 'wb') as dtout:
                        output=subprocess.check_output(dtargs, shell=False)
                        dtout.write(output)
                    tempFiles.append(dtoutfile)
                except:
                    # An error occurred running dnstwist
                    ## Need to test if dnstwist exists.  If not, raise exception.
                    print "Unexpected error running dnstwist:", sys.exc_info()[0]
                    pass
    
def parseOutput(docRoot, knownDomains, resultsFile, urlcrazy, dnstwist):

    # set up domains dictionary
    domains = []

    # compare known domains to discovered domains
    knowndom = []
    with open (knownDomains, 'rbU') as domfile:
        reader = csv.DictReader(domfile)
        for row in reader:
            knowndom.append(row['Domain'])

    if urlcrazy:
        # Read all urlcrazy .uctmp into dictionary
        ucfiledict = []
        for f in os.listdir(docRoot):
            if f.endswith(".uctmp"):
                ucfiledict.append(os.path.join(docRoot, f))

        # Parse each file in urlcrazy dictionary
        for file in ucfiledict:
            with open (file, 'rbU') as csvfile:
                reader = csv.DictReader(row.replace('\0', '') for row in csvfile)
                for row in reader:
                    if len(row) != 0:
                        if row['CC-A'] != "?":
                            if row['Typo'] in knowndom:
                                pass
                            else:
                                domains.append(row['Typo'])

    if dnstwist:
        dtfiledict = []
        for f in os.listdir(docRoot):
            if f.endswith(".dttmp"):
                dtfiledict.append(os.path.join(docRoot, f))

        # Parse each file in dnstwist dictionary
        for file in dtfiledict:
            with open (file, 'rbU') as csvfile:
                reader = csv.reader(csvfile)
                next(reader) # skip header line
                next(reader) # skip second line, contains original domain
                for row in reader:
                    if row[1] in knowndom:
                        pass
                    else:
                        domains.append(row[1])
                        
    # dedupe domains list
    domains = dedup(domains)
    
    # write out results
    # this file will only contain the header if there are no new results
    with open(resultsFile, 'wb') as outfile:
        fieldnames = ['Domain']
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in domains:
            writer.writerow({'Domain': row})
    outfile.close()

def sendMail(resultsFile):

    '''
            sendMail sends the results of urlcrazy scans,
            including diffs to your selected address
            using a given address.

            Specify your sending account username in mail_user.
            Specify your account password in mail_pwd.

            Configure for your mail server by modifying the
            mailServer = line.

            This assumes your mail server supports starttls.
            Future versions will allow you to specify whether
            or not to use starttls. To suppress starttls,
            remove the line mailServer.starttls().

    '''

    mail_user = "mail_sender_account"
    mail_pwd = "your_pass_here"
    mail_recip = ["recipient_address_1", "recipient_address_2"]

    def mail(to, subject, text, attachment, numResults):
            msg = MIMEMultipart()

            msg['From'] = mail_user
            msg['To'] = ", ".join(to)
            msg['Subject'] = subject

            msg.attach(MIMEText(text))

            # Attach the attachment if there are new results
            # numResults is the number of rows in the results file
            # This is always at least 1 due to the header row
            if numResults >= 2:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(open(attachment, 'rb').read())
                Encoders.encode_base64(part)
                part.add_header('Content-Disposition',
                        'attachment; filename="%s"' % os.path.basename(attachment))
                msg.attach(part)
            else:
                pass

            mailServer = smtplib.SMTP("smtp.gmail.com", 587)
            mailServer.ehlo()
            mailServer.starttls()
            mailServer.ehlo()
            mailServer.login(mail_user, mail_pwd)
            mailServer.sendmail(mail_user, to, msg.as_string())
            # Should be mailServer.quit(), but that crashes...
            mailServer.close()

    # define our attachment
    attachment = resultsFile
    
    # this counts the number of line in the results file
    # if it is 1, there were no results
    numResults = sum(1 for line in open(attachment))
    if numResults == 1:
        mail(mail_recip,
                "Daily DNS typosquatting recon report", # subject line
                "There were no new results in today's scan", # your message here
                attachment, numResults)

    else:
        mail(mail_recip,
                "Daily DNS typosquatting recon report", # subject line
                "The results from today's DNS typosquatting scan are attached", # your message here
                attachment, numResults)

def doCleanup(docRoot):
    # Delete all temporary .tmp files created by urlcrazy
    # Read all .tmp into dictionary
    filedict = []
    for f in os.listdir(docRoot):
        if ( (f.endswith(".uctmp")) or (f.endswith(".dttmp")) ):
            filedict.append(os.path.join(docRoot, f))
    for f in tempFiles:
        try:
            os.remove(f)
        except OSError:
            print "Error removing temporary file: " + f
            pass

def dedup(domainslist, idfun=None): # code from http://www.peterbe.com/plog/uniqifiers-benchmark
    if idfun is None:
        def idfun(x): return x
    seen = {}
    result = []
    for item in domainslist:
        marker = idfun(item)
        # in old Python versions:
        # if seen.has_key(marker)
        # but in new ones:
        if marker in seen: continue
        seen[marker] = 1
        result.append(item)
    return result

def main():

    # Set up parser for command line arguments
    parser = argparse.ArgumentParser(prog='crazyParser.py', description='crazyParser - a tool to detect new typosquatted domain registrations by using the output from dnstwist and/or urlcrazy', add_help=True)
    parser.add_argument('-c', '--config', help='Directory location for required config files', default=os.getcwd(), required=False)
    parser.add_argument('-o', '--output', help='Save results to file, defaults to results.csv', default='results.csv', required=False)
    parser.add_argument('-d', '--directory', help='Directory for saving output, defaults to current directory', default=os.getcwd(), required=False)
    parser.add_argument('-m', '--email', help='Email results upon completion, defaults to False', action="store_true", default=False, required=False)
    parser.add_argument('--dnstwist', help='Use dnstwist for domain discovery, defaults to False', action="store_true", default=False, required=False)
    parser.add_argument('--urlcrazy', help='Use urlcray for domain discovery, defaults to False', action="store_true", default=False, required=False)

    if  len(sys.argv)==1:
        parser.print_help()
        sys.exit(1)
    args = parser.parse_args()

    if args.config != os.getcwd():
        if os.path.isdir(args.config):
            configDir = args.config
        else:
            print "ERROR! Specified configuration directory " + args.config + " does not exist!"
            print "Exiting..."
            sys.exit()
    else:
        configDir = args.config

    if args.directory != os.getcwd():
        if os.path.isdir(args.directory):
            docRoot = args.directory
        else:
            print "ERROR! Specified output directory " + args.directory + " does not exist!"
            print "Exiting..."
            sys.exit()
    else:
        docRoot = args.directory

    # set up global files
    resultsFile = os.path.join(docRoot, args.output)
    myDomains = os.path.join(configDir,'mydomains.csv')
    knownDomains = os.path.join(configDir,'knowndomains.csv')

    # Check to make sure we have the necessary permissions
    checkPerms(docRoot, resultsFile)

    # Check dependencies
    checkDepends(myDomains, knownDomains, args.urlcrazy, args.dnstwist)
    
    # Make sure to clean up any stale output files
    doCleanup(docRoot)

    # Clean up output files at exit
    atexit.register(doCleanup, docRoot)
    
    # Execute discovery
    doCrazy(docRoot, resultsFile, myDomains, args.urlcrazy, args.dnstwist)

    # parse output
    parseOutput(docRoot, knownDomains, resultsFile, args.urlcrazy, args.dnstwist)

    # send results if -m/--email is true
    if args.email == True:
        sendMail(resultsFile)
    else:
        pass

if __name__ == "__main__":
    main()
