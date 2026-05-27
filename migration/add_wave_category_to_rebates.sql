-- Add wave_category to rebates if it does not already exist.
IF NOT EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.rebates')
      AND name = 'wave_category'
)
BEGIN
    ALTER TABLE dbo.rebates
    ADD wave_category VARCHAR(100) NULL;

    CREATE INDEX idx_rebates_wave_category ON dbo.rebates (wave_category);
END
