DROP TRIGGER IF EXISTS trigger_notify_lesson_change ON scheduler_lesson;
DROP FUNCTION IF EXISTS notify_lesson_change;

CREATE OR REPLACE FUNCTION notify_lesson_change() RETURNS TRIGGER AS $$
BEGIN
    -- Вставляем в таблицу уведомлений данные для рассылки
    INSERT INTO scheduler_lesson_notification_queue  (group_id, teacher_id, period_id, notification_dat, is_notified)
    VALUES (NEW.group_id, NEW.teacher_id, NEW.period_id, CURRENT_DATE, false)
    ON CONFLICT (group_id, teacher_id, period_id)
    DO NOTHING;  -- Избегаем дублирования
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_notify_lesson_change
AFTER INSERT OR UPDATE ON scheduler_lesson
FOR EACH ROW EXECUTE FUNCTION notify_lesson_change();
