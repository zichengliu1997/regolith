"""Helper for listing the to-do tasks. Tasks are gathered from people.yml, milestones, and group meeting actions.

"""
import datetime as dt
import dateutil.parser as date_parser
import math
import sys
from dateutil.relativedelta import *

from regolith.dates import get_due_date, get_dates
from regolith.helpers.basehelper import SoutHelperBase
from regolith.fsclient import _id_key
from regolith.tools import (
    all_docs_from_collection,
    get_pi_id,
    document_by_value,
)

TARGET_COLL = "people"
TARGET_COLL2 = "projecta"
TARGET_COLL3 = "meetings"
HELPER_TARGET = "l_todo"
Importance = [0, 1, 2]
ALLOWED_STATI = ["started", "finished", "cancelled"]


def subparser(subpi):
    subpi.add_argument("--all", action="store_true",
                       help="List both completed and uncompleted tasks. ")
    subpi.add_argument("-s", "--short_tasks", nargs='?', const=30,
                       help='Filter tasks with estimated duration <= 30 mins, but if a number is specified, the duration of the filtered tasks will be less than that number of minutes.')
    subpi.add_argument("-a", "--assigned_to",
                       help="Filter tasks that are assigned to this user id. Default id is saved in user.json. ")
    subpi.add_argument("-c", "--certain_date",
                       help="Enter a certain date so that the helper can calculate how many days are left from that date to the deadline. Default is today.")

    return subpi


class TodoListerHelper(SoutHelperBase):
    """Helper for listing the to-do tasks. Tasks are gathered from people.yml, milestones, and group meeting actions.
    """
    # btype must be the same as helper target in helper.py
    btype = HELPER_TARGET
    needed_dbs = [f'{TARGET_COLL}', f'{TARGET_COLL2}', f'{TARGET_COLL3}']

    def construct_global_ctx(self):
        """Constructs the global context"""
        super().construct_global_ctx()
        gtx = self.gtx
        rc = self.rc
        if "groups" in self.needed_dbs:
            rc.pi_id = get_pi_id(rc)
        rc.coll = f"{TARGET_COLL}"
        try:
            if not rc.database:
                rc.database = rc.databases[0]["name"]
        except:
            pass
        colls = [
            sorted(
                all_docs_from_collection(rc.client, collname), key=_id_key
            )
            for collname in self.needed_dbs
        ]
        for db, coll in zip(self.needed_dbs, colls):
            gtx[db] = coll
        gtx["all_docs_from_collection"] = all_docs_from_collection
        gtx["float"] = float
        gtx["str"] = str
        gtx["zip"] = zip

    def sout(self):
        rc = self.rc
        if not rc.assigned_to:
            try:
                rc.assigned_to = rc.default_user_id
            except AttributeError:
                print(
                    "Please set default_user_id in '~/.config/regolith/user.json', or you need to enter your group id "
                    "in the command line")
                return
        try:
            person = document_by_value(all_docs_from_collection(rc.client, "people"), "_id", rc.assigned_to)
            gather_todos = person.get("todos", [])
        except:
            print(
                "The id you entered can't be found in people.yml.")
            return
        if not rc.certain_date:
            today = dt.date.today()
        else:
            today = date_parser.parse(rc.certain_date).date()

        for projectum in self.gtx["projecta"]:
            if projectum.get('lead') != rc.assigned_to:
                continue
            projectum["deliverable"].update({"name": "deliverable"})
            gather_miles = [projectum["kickoff"], projectum["deliverable"]]
            gather_miles.extend(projectum["milestones"])
            for ms in gather_miles:
                if projectum["status"] not in ["finished", "cancelled"]:
                    if ms.get('status') not in \
                            ["finished", "cancelled"]:
                        due_date = get_due_date(ms)
                        ms.update({
                            'id': projectum.get('_id'),
                            'due_date': due_date,
                        })
                        ms.update({'description': f'milestone: {ms.get("name")} ({ms.get("id")})'})
                        gather_todos.append(ms)

        for todo in gather_todos:
            if not todo.get('importance'):
                todo['importance'] = 1
            if type(todo["due_date"]) == str:
                todo["due_date"] = date_parser.parse(todo["due_date"]).date()
            todo["days_to_due"] = (todo.get('due_date') - today).days
            todo["order"] = todo['importance'] + 1 / (1 + math.exp(abs(todo["days_to_due"])))

        gather_todos = sorted(gather_todos, key=lambda k: (-k['order']))

        if rc.short_tasks:
            for todo in gather_todos[::-1]:
                if todo.get('duration') is None or float(todo.get('duration')) > float(rc.short_tasks):
                    gather_todos.remove(t)
        num = 1
        print("-" * 50)
        print("    action (days to due date|importance|expected duration(mins))")
        for todo in gather_todos:
            if todo.get('status') not in ["finished", "cancelled"]:
                print(
                    f"{num:>2}. {todo.get('description')}({todo.get('days_to_due')}|{todo.get('importance')}|{str(todo.get('duration'))})")
                if todo.get('notes'):
                    for note in todo.get('notes'):
                        print(f"     - {note}")
                num += 1
        if rc.all:
            for todo in person.get("todos", []):
                if todo.get('status') in ["finished", "cancelled"]:
                    print(f"{num:>2}. ({todo.get('status')}) {todo.get('description')}")
                    if todo.get('notes'):
                        for note in todo.get('notes'):
                            print(f"     - {note}")
                    num += 1
        print("-" * 50)
        return
