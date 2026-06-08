CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;



DROP TRIGGER IF EXISTS trg_update_updated_at ON memories_v2;

CREATE TRIGGER trg_update_updated_at
BEFORE UPDATE ON memories_v2
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();