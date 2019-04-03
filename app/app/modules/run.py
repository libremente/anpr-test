""" This file contains the runner """
import logging
import sys
import yaml
from datetime import datetime
import businesstime
from dateutil import parser
from app.modules.utils import *
from app.modules.githubapi import *

"""
1. Triage
    a. no-triage
    If the issue has not been assigned yet, and it does not have an
    'avvisi' flag, then a fine occurs.
    b. late-triage
    If the issue has been assigned late (delta > 1 day), a late triage
    fine occurs.
2. Solution
    If there are not comments and delta > 2 days, a fine occurs
"""

def main(force=False):
    """ Loop on each issue, extract info, call templating function"""
     # Set variables
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    since = '2019-01-01T00:00:00'
    no_triage = 0
    late_triage = 0
    sol_fine = 0

    # Load cred from file

    my_path = path.abspath(path.dirname(__file__))

    with open(path.join(my_path, PRIVATE_DIR + "conf.yaml"), 'r') as f_in:
        yamlContent = yaml.load(f_in, Loader=yaml.FullLoader)
        CLIENT_ID = yamlContent['CLIENT_ID']
        CLIENT_SECRET = yamlContent['CLIENT_SECRET']
        ORGANIZATION = yamlContent['ORGANIZATION']
        REPO_NAME = yamlContent['REPO_NAME']
        STATE = yamlContent['STATE']
        NAMES = yamlContent['NAMES']
        RESERVED_LABELS = yamlContent['RESERVED_LABELS']

    # Check DB
    db = check_db()
    if db != False:
        diff = datetime.now().date() - parser.parse(db).date()
        # Leave a 5 days span between 2 interactions (if not forcing)
        if diff.days < 5 and not force:
            logging.info("Week already covered. Closing")
            return
        since = str(db, 'utf-8')

    # Load Api Object and get issues
    ghapi = GithubApi(CLIENT_ID, CLIENT_SECRET)
    issues = ghapi.get_issues(ORGANIZATION, REPO_NAME, STATE, since)
    bt = businesstime.BusinessTime()
    dict_list = []

    # Main loop over all issues
    for i in issues:
        fine_flag = False
        d = {}
        # Get events
        logging.info("Processing... %s" % i['title'])
        d['title'] = i['title']
        d['url'] = i['html_url']
        d['created_at'] = parser.parse(i['created_at'], ignoretz=True)

        # Labels - If 'avvisi', go to next issue
        if check_label(i['labels'], RESERVED_LABELS):
            continue

        # 1.a. - no-triage
        if not i['assignee']:
            delta = bt.businesstimedelta(d['created_at'], datetime.now())

            if delta.days != 0:
                d['no_triage'] = delta.days*50
                no_triage += d['no_triage']
                fine_flag = True
                logging.info("### Penale TRIAGE: %s" % d['no_triage'])
        # 1.b - late-triage
        else:
            d['assignee'] = i['assignee']['login']
            # Get events
            events = ghapi.get_url(i['events_url'])
            if i['assignee']['login'] in NAMES and events:
                for e in events:
                    if(e['event'] == 'assigned'):
                        d['assigned_on'] = parser.parse(e['created_at'], ignoretz=True)
                        delta = bt.businesstimedelta(d['created_at'], d['assigned_on'])
                        if delta.days != 0:
                            d['late_triage'] = calculate_fine(delta.days)
                            late_triage+= d['late_triage']
                            fine_flag = True
                            logging.info("### Penale Late TRIAGE: %s" % d['late_triage'])

        # 2 Solution
        # If there are not comments and delta > 2 days, a fine occurs
        d['comments'] = i['comments']
        if i['comments'] == 0:
            delta = bt.businesstimedelta(d['created_at'], datetime.now())

            if delta.days >= 2:
                d['sol_fine'] = calculate_fine(delta.days)
                logging.info("### Penale SOLUZIONE: %s" % d['sol_fine'])
                sol_fine += d['sol_fine']
                fine_flag = True

        if fine_flag: 
            dict_list.append(d)

    # Call Renderer and process files
    tpl_render(dict_list, no_triage, late_triage, sol_fine, since)
    move_files()
    write_db()

# Call main
if __name__ == "__main__":
    main()
