---
title: "Inventory Availability SOP"
doc_type: "sop"
doc_key: "sop_inventory_availability_001"
audience: "support"
status: "published"
source_name: "internal_wiki"
source_path: "/sops/inventory-availability-sop"
version: 1
---

# **Inventory Availability S**OP

## **Purpo**se

This SOP defines how support and commerce operations teams should interpret and communicate product availability information when handling customer-facing o**r** internal inventory questions.

## **When to Use This SOP**

Use this SOP when a support or operations user needs to:  
\- confirm whether a product is currently available  
\- explain low-stock or out-of-stock status  
\- interpret differences between inventory locations  
\- decide whether an inventory-related issue should be escalated

## **Availability Definitions**

For v1 operational use, availability should be interpreted as follows:  
\- in\_stock: quantity available is healthy and orderable under normal conditions  
\- low\_stock: quantity available exists but is limited and may change quickly  
\- out\_of\_stock: no available inventory is currently orderable  
\- unavailable: inventory status cannot be trusted because of an active issue, stale feed, or unresolved operational problem

Support should avoid promising future availability unless a documented operational source explicitly supports that statement.

## **Standard Lookup Process**

1\. Resolve the product to a canonical record.  
2\. Check current inventory availability across relevant locations.  
3\. Determine whether the result is stable, low-stock, or unavailabl**e.**  
4\. Check for known inventory incidents or feed delays if the result appears inconsistent.  
5\. Provide the supported internal answer or escalate if the data may be unreliable.

## **Interpreting Location Results**

Location-specific inventory may differ across fulfillment centers or distribution nodes. Support should use the summarized availability result unless a location-level explanation is operationally necessary.

Use caution when:  
\- one location shows stock but the primary shipping region is constrained  
\- inventory is low and may change before order placement  
\- availability differs from what a recent customer interaction or product page suggested

## **Low-Confidence Inventory Cases**

Treat inventory as low confidence when:  
\- there is an active inventory feed or sync incident  
\- the product page and structured inventory lookup disagree materially  
\- multiple recent cases suggest stale inventory data  
\- the product is part of a recent launch or allocation-sensitive release

In low-confidence cases, support should not overstate availability and should document that data may be under review.

## **Escalation Rules**

Escalate when:  
\- structured inventory data appears stale or contradictory  
\- multiple products are affected by the same availability anomaly  
\- customer promises could be impacted by unreliable stock data  
\- the issue appears related to a broader incident rather than a single product record

## **Customer Communication Guidance**

Internal users should communicate availability carefully:  
\- describe current availability, not guaranteed future availability  
\- note when stock is limited  
\- avoid absolute commitments when inventory confidence is low  
\- reference operational review when inventory reliability is under investigation

## **Ownership and Review**

This SOP is owned by Commerce Operations and should be reviewed after major inventory feed incidents, fulfillment changes, or product availability process changes.