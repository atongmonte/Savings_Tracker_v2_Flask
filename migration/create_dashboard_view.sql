/* =============================================================================
   vw_initiative_dashboard
   Matches the column layout of the legacy prod view so that any downstream
   reports / tools can point to savingstracker_v2 without code changes.

   Column mapping (old prod → new savingstracker_v2):
     INITIATIVE_MASTER     → initiatives            (alias I)
     INITIATIVE_COST_SAVINGS → cost_savings         (alias CS)
     INITIATIVE_COST_AVOIDANCE → cost_avoidance     (alias CA)
     INITIATIVE_REBATES    → rebates                (alias RB)
     *_ALLOC cols          → facility_allocations   (one JOIN per facility)
   ============================================================================= */

CREATE OR ALTER VIEW dbo.vw_initiative_dashboard AS
SELECT
    I.id                                                AS InitiativeID
  , U_OWNER.full_name                                   AS InitiativeOwner
  , I.initiative_type                                   AS Initiative_Type
  , I.description                                       AS Initiative_Desc
  , I.wave_id                                           AS Wave_ID
  , I.created_at                                        AS CreateTime
  , I.updated_at                                        AS LastUpdateTime
  , U_REV.full_name                                     AS ReviewedBy
  , I.status                                            AS STATUS
  , I.review_comments                                   AS LastReviewComments
  , I.review_date                                       AS LastReviewStatusChangeTime
  , I.is_deleted                                        AS IsDeleted
  , U_CRE.full_name                                     AS Created_By

    /* ── Cost Savings type ─────────────────────────────────────────────── */
  , CASE WHEN I.initiative_type = 'Cost Savings'
         THEN CS.savings_type   ELSE NULL END           AS Cost_Savings_Type_CS

    /* ── Contract Number ───────────────────────────────────────────────── */
  , CASE
        WHEN I.initiative_type = 'Cost Savings'   THEN CS.contract_number
        WHEN I.initiative_type = 'Cost Avoidance' THEN CA.contract_number
        WHEN I.initiative_type = 'Rebate'         THEN RB.contract_number
        ELSE NULL
    END                                                 AS Contract_Number

    /* ── Contract Category ─────────────────────────────────────────────── */
  , CASE
        WHEN I.initiative_type = 'Cost Savings'   THEN CS.contract_category
        WHEN I.initiative_type = 'Cost Avoidance' THEN CA.contract_category
        WHEN I.initiative_type = 'Rebate'         THEN RB.contract_category
        ELSE NULL
    END                                                 AS Contract_Category

    /* ── Contract Source ───────────────────────────────────────────────── */
  , CASE
        WHEN I.initiative_type = 'Cost Savings'   THEN CS.contract_source
        WHEN I.initiative_type = 'Cost Avoidance' THEN CA.contract_source
        WHEN I.initiative_type = 'Rebate'         THEN RB.contract_source
        ELSE NULL
    END                                                 AS Contract_Source

    /* ── GPO Tier ──────────────────────────────────────────────────────── */
  , CASE
        WHEN I.initiative_type = 'Cost Savings' THEN CS.gpo_tier
        WHEN I.initiative_type = 'Rebate'       THEN RB.gpo_tier
        ELSE NULL
    END                                                 AS GPO_Tier

    /* ── Cost Savings – financial ──────────────────────────────────────── */
  , CASE WHEN I.initiative_type = 'Cost Savings'
         THEN CS.baseline_spend  ELSE NULL END          AS Baseline_Spend_CS
  , CASE WHEN I.initiative_type = 'Cost Savings'
         THEN CS.expected_spend  ELSE NULL END          AS Expected_Spend_CS
  , CASE WHEN I.initiative_type = 'Cost Savings'
         THEN CS.is_fixed_cost   ELSE NULL END          AS fixed_Cost_Flag_CS

    /* ── Cost Avoidance – specific columns ─────────────────────────────── */
  , CASE WHEN I.initiative_type = 'Cost Avoidance'
         THEN CA.avoidance_type      ELSE NULL END      AS Cost_Avoidance_Type_CA
  , CASE WHEN I.initiative_type = 'Cost Avoidance'
         THEN CA.strata_project_id   ELSE NULL END      AS Strata_Proj_ID_CA
  , CASE WHEN I.initiative_type = 'Cost Avoidance'
         THEN CA.po_number           ELSE NULL END      AS PO_num_CA
  , CASE WHEN I.initiative_type = 'Cost Avoidance'
         THEN CA.po_date             ELSE NULL END      AS PO_Date_CA
  , CASE WHEN I.initiative_type = 'Cost Avoidance'
         THEN CA.original_quote      ELSE NULL END      AS Original_Quote_CA
  , CASE WHEN I.initiative_type = 'Cost Avoidance'
         THEN CA.new_quote           ELSE NULL END      AS New_Quote_CA

    /* ── Rebate – specific columns ─────────────────────────────────────── */
  , CASE WHEN I.initiative_type = 'Rebate'
         THEN RB.rebate_type   ELSE NULL END            AS Rebates_Type_RB
  , CASE WHEN I.initiative_type = 'Rebate'
         THEN RB.check_number  ELSE NULL END            AS Check_Number_RB

    /* ── Vendor Name ───────────────────────────────────────────────────── */
  , CASE
        WHEN I.initiative_type = 'Cost Savings'   THEN CS.vendor_name
        WHEN I.initiative_type = 'Cost Avoidance' THEN CA.vendor_name
        WHEN I.initiative_type = 'Rebate'         THEN RB.vendor_name
        ELSE NULL
    END                                                 AS Vendor_Name

    /* ── Start Date ────────────────────────────────────────────────────── */
    /*    CS → start_date, CA → avoidance_date, RB → rebate_check_date     */
  , CASE
        WHEN I.initiative_type = 'Cost Savings'   THEN CAST(CS.start_date        AS DATETIME)
        WHEN I.initiative_type = 'Cost Avoidance' THEN CAST(CA.avoidance_date    AS DATETIME)
        WHEN I.initiative_type = 'Rebate'         THEN CAST(RB.rebate_check_date AS DATETIME)
        ELSE NULL
    END                                                 AS Start_Date

    /* ── End Date (Cost Savings only) ──────────────────────────────────── */
  , CASE WHEN I.initiative_type = 'Cost Savings'
         THEN CAST(CS.end_date AS DATETIME)  ELSE NULL END AS End_Date

    /* ── Savings Amount ─────────────────────────────────────────────────  */
    /*    CS → total_savings_amount                                          */
    /*    CA → avoidance_amount                                              */
    /*    RB → rebate_amount                                                 */
  , CASE
        WHEN I.initiative_type = 'Cost Savings'   THEN CS.total_savings_amount
        WHEN I.initiative_type = 'Cost Avoidance' THEN CA.avoidance_amount
        WHEN I.initiative_type = 'Rebate'         THEN RB.rebate_amount
        ELSE NULL
    END                                                 AS Savings_Amount

    /* ── Facility Allocations (pivoted from facility_allocations) ───────── */
    /*    In the new schema allocations are initiative-level (not per type)   */
    /*    so we simply expose the allocation_amount for each facility code.   */
  , FA_MMC.allocation_amount                            AS MMC_ALLOC
  , FA_BURKE.allocation_amount                          AS BURKE_ALLOC
  , FA_AECOM.allocation_amount                          AS AECOM_ALLOC
  , FA_MMVO.allocation_amount                           AS MMVO_ALLOC
  , FA_MSSO.allocation_amount                           AS MSSO_ALLOC
  , FA_NYACK.allocation_amount                          AS NYACK_ALLOC
  , FA_SLCH.allocation_amount                           AS SLCH_ALLOC
  , FA_WPH.allocation_amount                            AS WPH_ALLOC

  , GETDATE()                                           AS DASHBOARD_UPDATE_TIME

FROM initiatives AS I

/* ── User joins ─────────────────────────────────────────────────────────── */
LEFT JOIN users AS U_OWNER ON I.owner_id       = U_OWNER.id
LEFT JOIN users AS U_CRE   ON I.created_by_id  = U_CRE.id
LEFT JOIN users AS U_REV   ON I.reviewed_by_id = U_REV.id

/* ── Type-specific detail tables ────────────────────────────────────────── */
LEFT JOIN cost_savings   AS CS ON I.id = CS.initiative_id
LEFT JOIN cost_avoidance AS CA ON I.id = CA.initiative_id
LEFT JOIN rebates        AS RB ON I.id = RB.initiative_id

/* ── Facility allocation pivots (one LEFT JOIN per facility code) ────────── */
LEFT JOIN facility_allocations AS FA_MMC
    ON FA_MMC.initiative_id  = I.id
   AND FA_MMC.facility_id    = (SELECT id FROM facilities WHERE code = 'MMC')

LEFT JOIN facility_allocations AS FA_BURKE
    ON FA_BURKE.initiative_id = I.id
   AND FA_BURKE.facility_id   = (SELECT id FROM facilities WHERE code = 'BURKE')

LEFT JOIN facility_allocations AS FA_AECOM
    ON FA_AECOM.initiative_id = I.id
   AND FA_AECOM.facility_id   = (SELECT id FROM facilities WHERE code = 'AECOM')

LEFT JOIN facility_allocations AS FA_MMVO
    ON FA_MMVO.initiative_id  = I.id
   AND FA_MMVO.facility_id    = (SELECT id FROM facilities WHERE code = 'MMVO')

LEFT JOIN facility_allocations AS FA_MSSO
    ON FA_MSSO.initiative_id  = I.id
   AND FA_MSSO.facility_id    = (SELECT id FROM facilities WHERE code = 'MSSO')

LEFT JOIN facility_allocations AS FA_NYACK
    ON FA_NYACK.initiative_id = I.id
   AND FA_NYACK.facility_id   = (SELECT id FROM facilities WHERE code = 'NYACK')

LEFT JOIN facility_allocations AS FA_SLCH
    ON FA_SLCH.initiative_id  = I.id
   AND FA_SLCH.facility_id    = (SELECT id FROM facilities WHERE code = 'SLCH')

LEFT JOIN facility_allocations AS FA_WPH
    ON FA_WPH.initiative_id   = I.id
   AND FA_WPH.facility_id     = (SELECT id FROM facilities WHERE code = 'WPH')

WHERE I.is_deleted = 0;
