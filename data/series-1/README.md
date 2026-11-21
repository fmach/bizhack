**Data Series**
This dataset contains two water flow time-series from an office building. The primary series (`flow`) records the main inlet flow into the facility, while the second series (`subflow`) isolates a specific internal leak caused by an automated swimming pool top-up mechanism.

**Format**
* timestamp,Datetime,"DD.MM.YYYY hh:mm:ss (e.g., 01.01.2000 00:00:25)"
* flow,Integer,Main inlet flow rate (flowmeter pulse factor: k = 10 l/pulse)
* subflow,Integer,Direct measurement of the pool top-up leakage flow rate

**Data Characteristics**
* **Building Type:** Commercial office building
* **Occupancy:** Approximately 100–200 active occupants during working hours
* **On-site Amenities:** Catering / gastro services, workshops, and a swimming pool