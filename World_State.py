from dataclasses import dataclass, field
from typing import List, Dict, Optional
import random
import simpy


# Constrants 
# ---------------------------------------------------------

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

#Available Skus, so far we have 5 products
ALL_SKUS = ["SKU-001", "SKU-002", "SKU-003", "SKU-004", "SKU-005", "SKU-006", "SKU-007", "SKU-008", "SKU-009", "SKU-010"]

#Inventory range per SKU per warehouse (Units)
INVENTORY_MIN = 0
INVENTORY_MAX = 200

# Pick-pack capacity per warehouse (units/hr)
PICKPACK_CAPACITY_RANGE = (20, 80)
 
# Carrier cutoff times in 24hr format (hour 14 = 2 PM)
# Simulation time is in hours from t=0 (start of day 1)
CARRIER_CUTOFF_HOUR = {
    "standard":  17,   # 5 PM
    "express":   15,   # 3 PM
    "next-day":  13,   # 1 PM
}
 
# Shipping delay probability per carrier service (0.0 – 1.0)
DELAY_PROBABILITY = {
    "standard": 0.10,
    "express":  0.05,
    "next-day": 0.03,
}
 
# Max delay in hours if a delay is triggered
MAX_DELAY_HOURS = {
    "standard": 48,
    "express":  24,
    "next-day": 12,
}
 
 
# Data Classes 
# ---------------------------------------------------------

@dataclass
class CarrierService:
    """A single shipping tier offered by a carrier."""

    name: str                    # e.g. "standard", "express", "next-day"
    base_cost: float             # fixed cost per shipment ($)
    cost_per_item: float         # variable cost per unit ($)
    transit_days: int            # nominal transit time in days
    cutoff_hour: int             # latest sim-hour carrier accepts orders today
    delay_probability: float     # chance of a disruption delay
    max_delay_hours: int         # worst-case delay added to transit time

@dataclass
class Carrier:
    """A carrier with multiple service tiers."""
    carrier_id: str
    name: str
    services: Dict[str, CarrierService] = field(default_factory=dict)
 
    def add_service(self, service: CarrierService):
        self.services[service.name] = service
 
 
@dataclass
class Reservation:
    """Locks inventory for an order to prevent double-allocation."""
    order_id: str
    warehouse_id: str
    sku: str
    quantity: int
    confirmed: bool = False


@dataclass
class Warehouse:
    """
    A fulfillment node with inventory, pick-pack capacity, and a work queue.
    capacity_resource is a SimPy Resource representing pick-pack slots.
    """
    warehouse_id: str
    location: str
    inventory: Dict[str, int]            # {sku: quantity}
    pickpack_rate: int                   # units per hour
    reservations: List[Reservation] = field(default_factory=list)
 
    # Set after SimPy env is created
    capacity_resource: Optional[simpy.Resource] = field(default=None, repr=False)
 
    def available_inventory(self, sku: str) -> int:
        """Units available = on-hand minus already reserved."""
        reserved = sum(
            r.quantity for r in self.reservations
            if r.sku == sku and not r.confirmed
        )
        return max(0, self.inventory.get(sku, 0) - reserved)
 
    def reserve(self, reservation: Reservation):
        self.reservations.append(reservation)
 
    def confirm_reservation(self, order_id: str):
        """Mark a reservation confirmed (picked & packed)."""
        for r in self.reservations:
            if r.order_id == order_id:
                r.confirmed = True
                self.inventory[r.sku] = max(0, self.inventory[r.sku] - r.quantity)
 
    def trigger_out_of_stock(self, sku: str):
        """Disruption: zero out a SKU to simulate a stock-out event."""
        if sku in self.inventory:
            print(f"  [DISRUPTION] {self.warehouse_id}: Out-of-stock triggered for {sku}")
            self.inventory[sku] = 0
 
 
@dataclass
class Order:
    """A customer order to be fulfilled."""
    order_id: str
    timestamp: float                  # sim time when order arrived
    items: Dict[str, int]             # {sku: quantity}
    promised_delivery_days: int       # SLA
    priority: bool = False
    status: str = "pending"           # pending | allocated | shipped | delivered | failed
    assigned_plan: Optional[dict] = field(default=None, repr=False)
 
 
 # World State
 #------------------------------------------------------------------------------------

class WorldState:
    """
    Central environment shared by all agents.
    Holds all warehouses, carriers, orders, and the SimPy environment.
    """
 
    def __init__(self):
        self.env = simpy.Environment()
        self.warehouses: Dict[str, Warehouse] = {}
        self.carriers: Dict[str, Carrier] = {}
        self.orders: List[Order] = []
        self.order_counter = 0
 
        self._build_warehouses()
        self._build_carriers()
 
    # ── Warehouse Setup ──────────────────────────────────────────────
 
    def _build_warehouses(self):
        """Create 5 warehouses with randomized inventory & capacity."""
        warehouse_defs = [
            ("WH-A", "North Hollywood"),
            ("WH-B", "Long Beach"),
            ("WH-C", "Downtown LA"),
            ("WH-D", "Santa Monica"),
            ("WH-E", "Monterey Park"),
        ]
 
        for wh_id, location in warehouse_defs:
            inventory = {
                sku: random.randint(INVENTORY_MIN, INVENTORY_MAX)
                for sku in ALL_SKUS
            }
            pickpack_rate = random.randint(*PICKPACK_CAPACITY_RANGE)
 
            wh = Warehouse(
                warehouse_id=wh_id,
                location=location,
                inventory=inventory,
                pickpack_rate=pickpack_rate,
            )
            # SimPy Resource: capacity = units/hr the warehouse can process
            wh.capacity_resource = simpy.Resource(self.env, capacity=pickpack_rate)
            self.warehouses[wh_id] = wh

    # ── Carrier Setup ────────────────────────────────────────────────
 
    def _build_carriers(self):
        """Create 3 carriers, each with standard / express / next-day tiers."""
        carrier_defs = [
            ("CAR-1", "TurboShip"),
            ("CAR-2", "BlueLine Services"),
            ("CAR-3", "EcoPath Delivery"),
        ]
        cost_profiles = {
            # (base_cost, cost_per_item) per service tier
            "standard":  [(4.99, 0.50), (5.49, 0.55), (3.99, 0.45)],
            "express":   [(9.99, 0.75), (10.49, 0.80), (8.99, 0.70)],
            "next-day":  [(19.99, 1.00), (21.99, 1.10), (18.99, 0.95)],
        }
        transit = {"standard": 5, "express": 2, "next-day": 1}
 
        for idx, (car_id, name) in enumerate(carrier_defs):
            carrier = Carrier(carrier_id=car_id, name=name)
            for svc_name in ("standard", "express", "next-day"):
                base, per_item = cost_profiles[svc_name][idx]
                svc = CarrierService(
                    name=svc_name,
                    base_cost=base,
                    cost_per_item=per_item,
                    transit_days=transit[svc_name],
                    cutoff_hour=CARRIER_CUTOFF_HOUR[svc_name],
                    delay_probability=DELAY_PROBABILITY[svc_name],
                    max_delay_hours=MAX_DELAY_HOURS[svc_name],
                )
                carrier.add_service(svc)
            self.carriers[car_id] = carrier
 
    
    # ── Order Factory ────────────────────────────────────────────────

    def create_order(self, items: Dict[str, int],
                     promised_delivery_days: int = 5,
                     priority: bool = False) -> Order:
        """Register a new order in the world state."""
        self.order_counter += 1
        order = Order(
            order_id=f"ORD-{self.order_counter:04d}",
            timestamp=self.env.now,
            items=items,
            promised_delivery_days=promised_delivery_days,
            priority=priority,
        )
        self.orders.append(order)
        return order
 
    # ── Disruption Triggers ──────────────────────────────────────────
 
    def trigger_shipping_delay(self, carrier_id: str, service_name: str) -> int:
        """
        Returns additional delay hours for a shipment.
        Called by the Carrier agent during shipping evaluation.
        """
        carrier = self.carriers.get(carrier_id)
        if not carrier:
            return 0
        svc = carrier.services.get(service_name)
        if not svc:
            return 0
        if random.random() < svc.delay_probability:
            delay = random.randint(1, svc.max_delay_hours)
            print(f"  [DISRUPTION] {carrier.name} / {service_name}: "
                  f"Shipping delay of {delay}h triggered.")
            return delay
        return 0
 
    def trigger_random_stockout(self):
        """
        Randomly zero out one SKU at one warehouse to simulate a supply disruption.
        """
        wh = random.choice(list(self.warehouses.values()))
        sku = random.choice(ALL_SKUS)
        wh.trigger_out_of_stock(sku)


'''

    # ── Debugging ─────────────────────────────────────────────
 
    def print_summary(self):
        """Print a readable snapshot of the current world state."""
        print("\n" + "=" * 60)
        print(f"WORLD STATE SNAPSHOT  (sim time: {self.env.now:.1f}h)")
        print("=" * 60)
 
        print("\n── WAREHOUSES ──────────────────────────────────────")
        for wh in self.warehouses.values():
            total_units = sum(wh.inventory.values())
            print(f"  {wh.warehouse_id} ({wh.location})")
            print(f"    Pick-pack rate : {wh.pickpack_rate} units/hr")
            print(f"    Total inventory: {total_units} units across {len(ALL_SKUS)} SKUs")
            for sku, qty in wh.inventory.items():
                avail = wh.available_inventory(sku)
                print(f"      {sku}: {qty} on-hand  ({avail} available)")
 
        print("\n── CARRIERS ────────────────────────────────────────")
        for car in self.carriers.values():
            print(f"  {car.carrier_id} — {car.name}")
            for svc in car.services.values():
                print(f"    [{svc.name:8s}]  "
                      f"base ${svc.base_cost:.2f} + ${svc.cost_per_item:.2f}/item  |  "
                      f"{svc.transit_days}d transit  |  "
                      f"cutoff hr {svc.cutoff_hour}  |  "
                      f"delay prob {svc.delay_probability:.0%}")
 
        print("\n── ORDERS ──────────────────────────────────────────")
        if not self.orders:
            print("  No orders yet.")
        for order in self.orders:
            print(f"  {order.order_id}  status={order.status}  "
                  f"priority={'YES' if order.priority else 'no'}  "
                  f"items={order.items}")
        print()
 
 
# ─────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────
 
if __name__ == "__main__":
    ws = WorldState()
 
    # Place a couple of sample orders
    ws.create_order({"SKU-001": 3, "SKU-004": 1}, promised_delivery_days=3, priority=True)
    ws.create_order({"SKU-002": 10}, promised_delivery_days=5)
    ws.create_order({"SKU-007": 2, "SKU-008": 5}, promised_delivery_days=7)
 
    # Print initial state
    ws.print_summary()
 
    # Simulate a couple of disruptions
    print("── TRIGGERING DISRUPTIONS ──────────────────────────")
    ws.trigger_random_stockout()
    ws.trigger_shipping_delay("CAR-1", "express")
    ws.trigger_shipping_delay("CAR-2", "next-day")
 
    print("\nState after disruptions:")
    ws.print_summary()

'''