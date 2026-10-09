"""The September enquiries as the facts a bot would have collected, plus the expected decision.

Each case is a list of turns. Each turn adds the facts learnt since the last tool call, and
states what the engine must decide at that point. `asked` counts are bumped automatically by
the replay harness after every ASK, exactly as the backend does on a live call.
Facts are taken only from what the caller actually said; nothing is invented. Where the
transcript never answers the bot's question, the follow-up turn is marked ASSUMED.
"""

CASES = {
    # ---------------------------------------------------------------- phone
    "T01": dict(date="2026-09-02", turns=[
        (dict(caller_name="Priya", referred_by="Shruti Joshi (client, Aundh)", project_category="residential",
              scope="full_home", locality="Kothrud, Dahanukar Colony", bhk=3, carpet_area_sqft=1400,
              deadline_text="by March", is_decision_maker=True), "QUALIFIED", None),
    ]),
    "T02": dict(date="2026-09-03", turns=[
        (dict(project_category="residential", scope="full_home", locality="Wakad", bhk=2, carpet_area_sqft=950,
              deadline_text="November", start_text="October", asked_price=True), "ASK", "deadline"),
        # ASSUMED: caller clarifies execution can finish after move-in, by end of January
        (dict(deadline_date="2027-01-31"), "QUALIFIED", None),
    ]),
    "T03": dict(date="2026-09-03", turns=[
        (dict(caller_name="Suresh Patil", project_category="residential", scope="partial", rooms_in_scope=2,
              locality="Nashik", is_decision_maker=True), "DECLINE", "service_area"),
    ]),
    "T04": dict(date="2026-09-04", turns=[
        (dict(project_category="residential", advice_only=True, rooms_in_scope=1), "DECLINE", "real_project"),
    ]),
    "T05": dict(date="2026-09-05", turns=[
        (dict(caller_name="Aarti Mehta", referred_by="Vikram Agarwal (close friend of Nikhil)",
              project_category="residential", scope="full_home", locality="Koregaon Park", bhk=4,
              carpet_area_sqft=2400, deadline_text="February", site_status="moved out, site free"),
         "QUALIFIED", None),
    ]),
    "T06": dict(date="2026-09-05", turns=[
        (dict(project_category="office", scope="office_fitout", locality="Baner", carpet_area_sqft=800,
              deadline_text="operational by December", site_status="bare shell", is_decision_maker=True),
         "QUALIFIED", None),
    ]),
    "T07": dict(date="2026-09-08", turns=[
        (dict(project_category="residential", scope="partial", rooms_in_scope=2,
              deadline_text="before Diwali"), "ASK", "area"),
        # ASSUMED: caller is in Pune (never asked on the real call)
        (dict(locality="Pune"), "ASK", "deadline"),          # festival name → ask for a date
        (dict(deadline_date="2026-11-08"), "ASK", "deadline_flexible"),
        (dict(deadline_flexible=True), "NURTURE", "timeline"),  # "What if I start after Diwali?"
    ]),
    "T08": dict(date="2026-09-09", turns=[
        (dict(), "ASK", "scope"),  # missed call at 10:47pm: the bot answers and starts qualifying
    ]),
    "T09": dict(date="2026-09-10", turns=[
        (dict(caller_name="Sheetal Deshpande", existing_client=True, complaint=True,
              existing_client_issue="Designer Aryan unresponsive 5 days; 2BHK Viman Nagar; wants Nikhil/senior callback"),
         "ESCALATE", "existing_client"),
    ]),
    "T10": dict(date="2026-09-11", turns=[
        (dict(project_category="residential", scope="partial", rooms_in_scope=2, locality="Kharadi", bhk=1,
              carpet_area_sqft=550, budget_max_inr=150000, is_decision_maker=True), "DECLINE", "budget"),
    ]),
    "T11": dict(date="2026-09-12", turns=[
        (dict(project_category="residential", scope="partial", rooms_in_scope=3, locality="Baner", bhk=2,
              structural_changes=False, is_decision_maker=True, site_status="rented, landlord OK, 3-yr lease"),
         "ASK", "deadline"),
        (dict(start_text="next month"), "QUALIFIED", None),  # ASSUMED answer
    ]),
    "T12": dict(date="2026-09-15", turns=[
        (dict(caller_name="Anand Sharma", project_category="residential", scope="full_home",
              locality="Kalyani Nagar", carpet_area_sqft=5500, deadline_text="March",
              site_status="new construction, empty", is_decision_maker=True), "QUALIFIED", None),
    ]),
    "T13": dict(date="2026-09-16", turns=[
        (dict(project_category="residential", scope="partial", rooms_in_scope=3, locality="Aundh", bhk=3,
              carpet_area_sqft=1100, asked_price=True), "ASK", "deadline"),
        (dict(deadline_text="by April"), "QUALIFIED", None),  # ASSUMED answer
    ]),
    "T14": dict(date="2026-09-17", turns=[
        (dict(project_category="residential", scope="full_home", locality="Hadapsar", bhk=3,
              is_decision_maker=False, decision_maker_will_attend=True, site_status="new possession"),
         "ASK", "deadline"),
        (dict(start_text="right away"), "QUALIFIED", None),  # ASSUMED answer
    ]),
    "T15": dict(date="2026-09-18", turns=[
        (dict(caller_name="Smita", project_category="residential", scope="full_home", locality="Undri", bhk=2,
              carpet_area_sqft=875, start_text="right away", authorised_by_decision_maker=True,
              site_status="possession in ~6 weeks, builder allows access"), "QUALIFIED", None),
    ]),
    "T16": dict(date="2026-09-19", turns=[
        (dict(caller_name="Girish Nair", project_category="residential", locality="Viman Nagar", bhk=3,
              repeat_caller_unanswered=True), "ASK", "scope"),
    ]),
    "T17": dict(date="2026-09-22", turns=[
        (dict(caller_name="Ritu Kapoor", project_category="residential", scope="partial", rooms_in_scope=3,
              locality="Pimple Saudagar", bhk=3, carpet_area_sqft=1050, deadline_text="by March"),
         "QUALIFIED", None),
    ]),
    "T18": dict(date="2026-09-23", turns=[
        (dict(project_category="office", scope="office_fitout", carpet_area_sqft=180, is_decision_maker=True),
         "DECLINE", "real_project"),
    ]),
    "T19": dict(date="2026-09-24", turns=[
        (dict(project_category="restaurant", locality="Koregaon Park"), "DECLINE", "real_project"),
    ]),
    "T20": dict(date="2026-09-25", turns=[
        (dict(caller_name="Pooja", project_category="residential", scope="full_home",
              locality="Magarpatta, Cybercity", bhk=2, carpet_area_sqft=900, start_text="January",
              is_decision_maker=True), "QUALIFIED", None),
    ]),
    # ---------------------------------------------------------------- web forms
    "F03": dict(date="2026-09-06", turns=[
        (dict(caller_name="Nilesh Dhamdhere", project_category="residential", scope="full_home",
              locality="Talegaon Dabhade, near Pune", bhk=3, carpet_area_sqft=1400,
              deadline_text="3-4 months", budget_max_inr=2000000), "DECLINE", "service_area"),
    ]),
    "F06": dict(date="2026-09-14", turns=[
        (dict(caller_name="Preethi Nair", project_category="residential", scope="partial", rooms_in_scope=6,
              locality="NIBM Road", bhk=4, carpet_area_sqft=1950, start_text="February 2027",
              budget_max_inr=4000000, is_decision_maker=True,
              extra_notes="Budget firm upward. 3 studios shortlisted. Wants honest aesthetic-fit talk: warm, earthy, minimal."),
         "QUALIFIED", None),
    ]),
    "F08": dict(date="2026-09-18", turns=[
        (dict(caller_name="Divya Hegde", project_category="residential", scope="partial", rooms_in_scope=2,
              locality="Wakad", bhk=2, carpet_area_sqft=875, deadline_text="3 weeks", deadline_flexible=False,
              budget_max_inr=500000), "DECLINE", "timeline"),
    ]),
}

PHONE = [k for k in CASES if k.startswith("T")]
FORMS = [k for k in CASES if k.startswith("F")]
