DECLARE @sql NVARCHAR(MAX) = N'';

SELECT @sql = @sql + '
IF OBJECT_ID(''[SavingsTracker_backup].[' + s.name + '].[' + t.name + ']'') IS NOT NULL
    DROP TABLE [SavingsTracker_backup].[' + s.name + '].[' + t.name + '];

SELECT *
INTO [SavingsTracker_backup].[' + s.name + '].[' + t.name + ']
FROM [SavingsTracker].[' + s.name + '].[' + t.name + '];
'
FROM SavingsTracker.sys.tables t
JOIN SavingsTracker.sys.schemas s
    ON t.schema_id = s.schema_id
WHERE s.name IN ('dbo','dev','prod','test');

EXEC sp_executesql @sql;