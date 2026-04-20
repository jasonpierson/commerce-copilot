---
title: "Customer Impact Assessment Runbook"
doc_type: "runbook"
doc_key: "runbook_customer_impact_assessment_001"
audience: "engineering_support"
status: "published"
source_name: "internal_wiki"
source_path: "/runbooks/customer-impact-assessment-runbook"
version: 1
---

# **Customer Impact Assessment Runbook**

## **Purpose**

This runbook defines how internal teams should assess and describe customer impact during an active operational incident. It is intended to improve consistency in incident summaries, escalation requests, and support guidance.

## **When to Use This Runbook**

Use this runbook when:  
\- an incident is active and customer impact is not yet well understood  
\- support or operations needs to summarize likely customer-facing consequences  
\- an escalation request requires a clear impact statement  
\- incident communication is at risk of being vague or inconsistent

## **Impact Assessment Questions**

The following questions should be answered as directly as possible:  
\- what customer action is failing, degraded, or delayed?  
\- which channel is affected?  
\- is the issue intermittent or persistent?  
\- how broad is the affected audience?  
\- are there safe workarounds?  
\- is the issue causing lost purchases, delayed refunds, failed returns, or other measurable harm?

## **Impact Categories**

Use one or more of the following categories when summarizing impact:  
\- conversion or checkout impact  
\- order management impact  
\- return or refund workflow impact  
\- product availability misinformation  
\- support volume increase  
\- reputational or trust risk

## **Evidence Sources**

Use available evidence such as:  
\- incident timeline events  
\- support case trends  
\- operational alerts  
\- structured workflow failure signals  
\- known affected channels or regions

Do not present speculation as confirmed fact. If uncertainty remains, state that clearly.

## **Writing the Impact Summary**

A good impact summary should:  
\- name the affected customer action  
\- state whether the issue is intermittent or persistent  
\- describe the likely scope in plain language  
\- note whether a workaround exists  
\- avoid overstating precision that the team does not actually have

Example strong summary:  
Customers on mobile web are experiencing intermittent checkout failures. Some customers can still complete purchases, but failure rate is elevated and support volume is rising.

Example weak summary:  
Checkout may be impacted for some users.

## **Escalation Thresholds**

Customer impact should be treated as escalation-supporting when:  
\- the issue blocks revenue-generating activity  
\- the issue is sustained and customer-facing  
\- the scope is unclear but early evidence suggests broad impact  
\- support volume or customer complaints are rising quickly  
\- prior mitigation attempts did not materially reduce impact

## **Output Requirements for Incident Summaries**

When an incident summary is generated, the impact section should ideally include:  
\- affected experience  
\- scope estimate in qualitative terms if precise numbers are unavailable  
\- whether the issue is ongoing or improving  
\- recommended next step if the impact justifies escalation or deeper review

## **Ownership and Review**

This runbook is owned by Commerce Operations and Engineering Support and should be reviewed after major incident postmortems or communication failures.