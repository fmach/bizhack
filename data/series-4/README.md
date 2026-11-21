**Data Serie**
This dataset contains a time-series record of water flow in an office building. It tracks a continuous baseline leakage during the initial period, a standard operating flow spike on Day 6, and a major pipe burst incident on Day 8 that subsequently resolved the long-term baseline leak.

**Format**
* timestamp,Datetime,"DD.MM.YYYY hh:mm:ss (e.g., 01.01.2000 00:00:25)"
* flow,String,"Main inlet flow rate with explicit volume unit (e.g., 2.20 L, 600 mL; flowmeter pulse factor: k = 0.1 l/pulse)"

**Data Characteristics**
* **Building Type:** Commercial office building
* **Days 1–5:** Continuous baseline water leak detected
* **Day 6:** Increased flow rate reflecting normal operational daytime usage
* **Day 8 (Major Incident):** Major pipe burst/failure occurs; following this event, the long-term baseline leak drops to zero