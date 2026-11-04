# Literature review

Starter list, grouped by the chapter it feeds. **Check every entry against the
original (title, year, venue, pages) before citing it**, and add what you find.
Target: 15-25 sources.

## Protocol specifications (Background)

- OASIS (2014). *MQTT Version 3.1.1.* OASIS Standard. QoS 0/1/2, clean session, persistent sessions.
- OASIS (2019). *MQTT Version 5.0.* OASIS Standard. Session expiry, message expiry, shared subscriptions.
- Fielding, R. T. (2000). *Architectural Styles and the Design of Network-based Software Architectures.* PhD thesis, UC Irvine. Origin of REST.
- Fielding, R., Nottingham, M., Reschke, J. (2022). *RFC 9110: HTTP Semantics.* IETF.
- Light, R. A. (2017). Mosquitto: server and client implementation of the MQTT protocol. *Journal of Open Source Software*, 2(13).

## Microservices and communication styles (Background / Motivation)

- Lewis, J., Fowler, M. (2014). *Microservices.* martinfowler.com.
- Dragoni, N. et al. (2017). Microservices: yesterday, today, and tomorrow. In *Present and Ulterior Software Engineering*, Springer.
- Newman, S. (2021). *Building Microservices*, 2nd ed. O'Reilly. Chapters on sync vs async communication.
- Eugster, P. T., Felber, P. A., Guerraoui, R., Kermarrec, A.-M. (2003). The many faces of publish/subscribe. *ACM Computing Surveys*, 35(2). Decoupling in time, space and synchronisation: the theory behind RQ2.
- Hohpe, G., Woolf, B. (2003). *Enterprise Integration Patterns.* Addison-Wesley.

## Resilience (RQ2)

- Nygard, M. T. (2018). *Release It!*, 2nd ed. Pragmatic Bookshelf. Timeouts, retries, circuit breakers, cascading failures.
- Kleppmann, M. (2017). *Designing Data-Intensive Applications.* O'Reilly. Delivery guarantees, at-least-once vs exactly-once.

## Prior MQTT vs HTTP comparisons (Related Work)

- Naik, N. (2017). Choice of effective messaging protocols for IoT systems: MQTT, CoAP, AMQP and HTTP. *IEEE ISSE*.
- Thangavel, D. et al. (2014). Performance evaluation of MQTT and CoAP via a common middleware. *IEEE ISSNIP*.
- Yokotani, T., Sasaki, Y. (2016). Comparison with HTTP and MQTT on required network resources for IoT. *ICCEREC*.

Most prior work is IoT and device-to-server. The gap your exposé names is
**service-to-service** communication in a backend. Look specifically for that.

## Measurement methodology (Methodology)

- Tene, G. *How NOT to Measure Latency* (conference talk). Coordinated omission, which is why the simulator sends open-loop.

## Search strings

Google Scholar, IEEE Xplore, ACM DL:

- `"MQTT" "microservices" performance`
- `"MQTT" "HTTP" latency comparison`
- `"publish/subscribe" microservices resilience`
- `"MQTT" "quality of service" evaluation`
- `asynchronous messaging microservices benchmark`

## Reading notes template

```
### <Author (Year)> <Short title>
- Question / goal:
- Setup (protocols, broker, hardware, load):
- Key results (numbers):
- Relevance to which RQ:
- Limitations / what they did not test:
```
