# Security policy

Please do not publish details of a suspected vulnerability before maintainers have had a reasonable opportunity to investigate.

Report vulnerabilities privately to the repository maintainers after the project owner configures a security contact or GitHub private vulnerability reporting. Do not include credentials, customer data or sensitive production artifacts in issue reports.

StageWatch runs locally and does not transmit data. It writes summary metadata to a local SQLite database when history is enabled. Treat the database and generated reports as potentially sensitive because they can contain stage names, exception messages, mapping keys, metadata and data-shape information.
