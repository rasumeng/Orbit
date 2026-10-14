# Orbit midpoint demo and presentation plan

## Five-minute presentation
1. Problem (45s): responsibilities scattered across Canvas, schedules, projects, work, organizations.
2. Architecture (60s): React -> API Gateway -> Lambda -> DynamoDB; CloudWatch; SAM/CloudFormation.
3. Implemented features (75s): create, list, complete; show API calls and data persistence.
4. Results and setbacks (60s): include *actual* screenshots, logs, test outcomes, deployment limitations.
5. Next steps (60s): Canvas one-time ICS import; auth; scheduled sync; reminders; smarter workload views.

## 5–10 minute demo
1. Show working React dashboard (1 minute).
2. Create example responsibility, category work or leadership (1 minute).
3. Refresh and show persistence (1 minute).
4. Mark complete and show updated totals (1 minute).
5. Open DynamoDB and point out exact record (1–2 minutes).
6. Show Lambda/CloudWatch log and API Gateway architecture (1–2 minutes).
7. Describe what's next, especially Canvas ICS and authenticated multi-user architecture (1 minute).

## Definition of done
- [ ] Deployment works in course AWS environment
- [ ] GET /health success
- [ ] POST /items successful
- [ ] GET /items persisted record
- [ ] PATCH /items/{id} successful
- [ ] React screen works after page refresh
- [ ] Screenshots, architecture, and logs captured
- [ ] README and repo updated, presentation named Group<group-number>-Orbit.pptx
- [ ] Demo video link uploaded via Canvas

## One-time Canvas ICS stretch
- Start with a downloaded fixture .ics with no private data.
- Parse VEVENT UID, SUMMARY, DTSTART, DTEND into normalized records.
- Deduplicate by stable source UID; preserve manual records.
- Validate file size, content, and date formats.
- Only after this works, evaluate Canvas feed URL retrieval with an allowlist and strict security rules.
