DECLARE @sql NVARCHAR(MAX) = N'';

------------------------------------------------------------
-- Step 1: Drop all existing tables in SavingsTracker_backup
------------------------------------------------------------
SELECT @sql = @sql + '
DROP TABLE [SavingsTracker_backup].[' + s.name + '].[' + t.name + '];'
FROM SavingsTracker_backup.sys.tables t
JOIN SavingsTracker_backup.sys.schemas s
    ON t.schema_id = s.schema_id
WHERE s.name IN ('dbo','dev','prod','test');

EXEC sp_executesql @sql;


------------------------------------------------------------
-- Step 2: Copy all tables from SavingsTracker to SavingsTracker_backup
------------------------------------------------------------
SET @sql = N'';

SELECT @sql = @sql + '
SELECT *
INTO [SavingsTracker_backup].[' + s.name + '].[' + t.name + ']
FROM [SavingsTracker].[' + s.name + '].[' + t.name + '];'
FROM SavingsTracker.sys.tables t
JOIN SavingsTracker.sys.schemas s
    ON t.schema_id = s.schema_id
WHERE s.name IN ('dbo','dev','prod','test');

EXEC sp_executesql @sql;