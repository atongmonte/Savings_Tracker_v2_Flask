/* =============================================================================
   system_event_logs
   Persistent log for system-level admin operations (e.g. running the daily
   distribution stored procedure).  Not tied to any individual initiative.
   ============================================================================= */

CREATE TABLE dbo.system_event_logs (
    id               INT           NOT NULL IDENTITY(1,1)
  , event_type       NVARCHAR(100) NOT NULL               -- e.g. 'DISTRIBUTION_PROC'
  , status           NVARCHAR(20)  NOT NULL               -- starting | waiting | running | success | failed
  , log_text         NVARCHAR(MAX) NULL                   -- full newline-delimited log
  , started_by       NVARCHAR(200) NULL                   -- username / full name
  , started_at       DATETIME2     NOT NULL DEFAULT GETDATE()
  , ended_at         DATETIME2     NULL
  , duration_seconds FLOAT         NULL

  , CONSTRAINT PK_system_event_logs PRIMARY KEY (id)
);

CREATE INDEX IX_system_event_logs_event_type ON dbo.system_event_logs (event_type);
CREATE INDEX IX_system_event_logs_started_at ON dbo.system_event_logs (started_at DESC);
