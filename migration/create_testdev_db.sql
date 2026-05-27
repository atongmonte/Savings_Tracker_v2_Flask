USE master;
GO

IF DB_ID(N'savingstracker_v2_testdev') IS NULL
BEGIN
    PRINT 'Creating database savingstracker_v2_testdev...';
    CREATE DATABASE [savingstracker_v2_testdev];
    PRINT 'Database created.';
END
ELSE
BEGIN
    PRINT 'Database savingstracker_v2_testdev already exists.';
END
GO
