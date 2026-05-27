-- Adds Finance role if it does not already exist
IF NOT EXISTS (SELECT 1 FROM user_roles WHERE name = 'Finance')
BEGIN
    INSERT INTO user_roles (
        name,
        description,
        can_create,
        can_edit_own,
        can_edit_all,
        can_delete_own,
        can_delete_all,
        can_review,
        can_approve,
        can_export,
        can_manage_users,
        created_at,
        updated_at
    )
    VALUES (
        'Finance',
        'Finance users with access to rebate extraction only',
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        GETDATE(),
        GETDATE()
    );
END
GO
