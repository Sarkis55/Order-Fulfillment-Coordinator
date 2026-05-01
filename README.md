# Order-Fulfillment-Coordinator
Order fulfillment may appear straightforward – receive the order, pick the item, ship the
package – but in practice, it is a complex coordination challenge shaped by varying
conditions. Each order requires multiple interdependent decisions, such as which
warehouse or store should fulfill it, whether orders containing multiple items should be
split across locations, how limited pick-pack capacity should be allocated, and which
shipping option can meet the promised delivery date without driving up costs. These
decisions are made under uncertainty, where inventory fluctuates, labor capacity varies,
carrier cut-off times impose constraints, and unexpected disruptions such as delays or
out-of-stock items. Conventional rule-based systems and rigid optimization models often
struggle in this environment because they rely on fixed logic that cannot adapt to
competing priorities and real-time changes.

This project approaches order fulfillment as a multi-agent system composed of
specialized decision-makers: an Order Intake agent that manages priorities and delivery
commitments, an Inventory agent tracking stock availability, a Pick-pack Capacity agent
modeling operational constraints, a Carrier/Shipping agent that evaluates delivery
options, and a Routing/Allocation Coordinator agent that orchestrates the final plan.
These agents interact and negotiate to generate fulfillment strategies that balance speed,
cost, and reliability. When conditions shift – such as limited stock or shipping delays –
The agents collaborate and adjust decisions. By simulating decentralized coordination and
adaptive planning, the project investigates how multi-agent approaches can create more
flexible, efficient, and resilient processes in a domain where no straightforward software
solution exists.

## Implementation:

First, create an environment or world state that includes dataclasses holding:
- Nodes (Warehouses A, B, C):
  - Inventory
  - Pick-pack capacity (units/hr)
  - Current_queue: (busy, free, etc.)
- Carriers with:
  - Services (standard, express, next-day shipping)
  - Cost model (base + per item/weight)
  - Cutoff time (when do they stop taking in orders to ship)
- Orders:
  - Order numbers, timestamps, SKUs, and quantities of items
  - Estimated delivery
  - Priority or not
- Reservations:
  - Prevents double allocation
  - Tracks the reserved quantity per warehouse per order.

Next would be to implement an event-driven simulation using the SimPy library, which is
a discrete event simulation framework, which will include components such as order
arrivals, pick/pack processing, shipping cutoffs, delivery times, and disruptions (delays,
out-of-stock, etc.)

- Implement Agents:
  - **Order Intake Agent:** Manages priorities and delivery commitments.
  - **Inventory Agent:** Tracks stock availability.
  - **Pick-pack Capacity Agent:** estimates readiness and checks available warehouses
that can fulfill the order.
  - **Carrier/Shipping Agent:** Evaluates delivery options
  - **Routing/Allocation Coordinator Agent:** orchestrates the plan and commits.
    
- The coordination algorithm (How the Coordinator runs per order)
  - Requests feasible nodes from the Inventory agent.
  - For each candidate node:
    - Asks the capacity agent for a readiness estimate
    - Asks the carrier agent for shipping options and cutoff time
  - Generates a plan for the order:
    - A single-node plan is preferable; otherwise, the plan will be split across
different nodes.
  - Scores each plan:
    - Metrics include lateness risk + cost + time-to-ship + split penalty
    - Selects the plan with the lowest score and processes the order.
