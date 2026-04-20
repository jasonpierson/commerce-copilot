---
title: "Mobile Checkout Incident Playbook"
doc_type: "incident_playbook"
doc_key: "incident_playbook_mobile_checkout_001"
audience: "engineering_support"
status: "published"
source_name: "internal_wiki"
source_path: "/playbooks/mobile-checkout-incident-playbook"
version: 1
---

# **Mobile Checkout Incident Playbook**

## **Purpose**

This playbook provides focused guidance for incidents that primarily affect mobile web checkout. It complements the general Checkout Incident Runbook by covering mobile-specific symptoms, likely failure patterns, and communication guidance.

## **Scope**

Use this playbook when evidence suggests the issue is concentrated in mobile web checkout, including cart-to-checkout transition failures, payment-step failures, or mobile-specific timeout behavior.

## **Common Symptoms**

Typical signals include:  
\- support reports that customers can browse products but cannot complete checkout on mobile devices  
\- elevated cart abandonment on mobile web without a matching desktop pattern  
\- intermittent payment-step errors that are not reproduced consistently on desktop  
\- sudden increases in support contacts mentioning mobile browser issues, repeated refresh attempts, or failed order completion

## **Immediate Actions**

1\. Confirm whether the issue reproduces on mobile web and whether desktop remains healthy.  
2\. Identify whether the issue affects all mobile browsers or a narrower set.  
3\. Check recent frontend configuration changes, checkout-related flags, and integration dependencies.  
4\. Review the current incident record or create one if customer impact meets incident criteria.  
5\. Assess whether support guidance should be updated immediately.

## **Known Failure Patterns**

Mobile checkout incidents commonly cluster around:  
\- browser-specific rendering or scripting issues  
\- payment or fraud-step errors that surface differently on mobile  
\- performance degradation on mobile checkout pages  
\- dependency issues that only become visible in mobile-specific interaction paths  
\- stale configuration or cache behavior after a recent release

## **Communication Guidance**

Internal summaries should state clearly:  
\- that the impact is mobile-specific unless broader evidence appears  
\- whether the issue is intermittent or persistent  
\- whether a workaround exists, such as retrying on desktop, only when confirmed safe  
\- whether the issue is under active mitigation or requires escalation

Do not imply that all checkout is broken if the current evidence only supports mobile impact.

## **Exit Criteria**

The playbook should be considered complete for an incident cycle when:  
\- the affected flow is stable on mobile web  
\- support guidance is updated or withdrawn as appropriate  
\- the incident summary includes customer impact, mitigation, and residual risk  
\- any follow-up work is captured for later remediation

## **Ownership and Review**

This playbook is owned by Engineering Support and Commerce Operations and should be reviewed after major mobile checkout incidents or frontend delivery changes.