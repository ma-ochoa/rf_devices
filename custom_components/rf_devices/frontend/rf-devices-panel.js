/* RF Devices panel: create RF devices, learn and clean their codes, export/import.
 * Plain web component, no build step. Talks to the rf_devices/* WebSocket commands.
 */

const I18N = {
  es: {
    title: "RF Devices",
    new_device: "Nuevo dispositivo",
    export: "Exportar",
    debug_report: "Diagnóstico",
    debug_report_help: "Descarga un informe para depurar a distancia: versiones, emisores, dispositivos ESPHome, entidades usadas, últimos envíos y capturas (con las ráfagas recibidas) y registro. No lleva contraseñas ni los códigos guardados; sí las ráfagas captadas durante las capturas.",
    import: "Importar",
    empty: "Aún no hay dispositivos. Crea uno y captura los botones de su mando.",
    edit: "Editar",
    delete: "Eliminar",
    confirm_delete: "¿Eliminar «{name}» y sus entidades?",
    back: "Volver",
    save: "Guardar",
    saved: "Guardado. Las entidades se están recargando…",
    close: "Cerrar",
    name: "Nombre",
    type: "Tipo",
    transmitter: "Emisor RF",
    default_tx: "Por defecto ({name})",
    device: "Dispositivo",
    buttons: "Botones del mando",
    t_light: "Luz",
    t_switch: "Enchufe / interruptor",
    t_cover: "Persiana / toldo",
    t_fan: "Ventilador",
    t_fan_light: "Ventilador con luz · un mando",
    group_fan: "Ventilador",
    group_light: "Luz",
    ha_devices: "Dispositivos en Home Assistant",
    open_device_help: "En la ficha puedes añadirlo a un panel de control con «Añadir al panel de control».",
    t_buttons: "Solo botones",
    mode: "Mando",
    mode_toggle: "Un botón que alterna",
    mode_onoff: "Botones de encender y apagar",
    switch_entity: "Interruptor de pared (opcional)",
    switch_entity_help: "Cada cambio de este interruptor enciende o apaga el dispositivo, esté en la posición que esté. Útil con una entrada de Shelly desacoplada.",
    none: "Ninguno",
    open_time: "Tiempo de subida (s)",
    close_time: "Tiempo de bajada (s)",
    times_help: "Con los dos tiempos se calcula la posición y se puede elegir un porcentaje (necesita el botón Parar).",
    cover_wiring_q: "¿Tiene relé o botones de pared?",
    cover_wiring_none: "Nada: solo el mando RF",
    cover_wiring_wall: "Solo botones de pared",
    cover_wiring_relay: "Un relé le da corriente",
    cover_wiring_relay_wall: "Relé y botones de pared",
    cover_relay_intro: "Todo es opcional. Sin nada de esto la persiana funciona por tiempo con el mando RF.",
    cover_relay_help: "Relé (Shelly, enchufe…) que da corriente al motor. Con el relé apagado no se envía nada.",
    cover_power_on: "Encender el relé cuando haga falta para mover la persiana",
    cover_power_up_delay_help: "Tiempo que se deja al receptor del motor para arrancar antes de enviar la orden.",
    cover_wall_type: "Tipo de botones",
    cover_wall_momentary: "Pulsadores (vuelven solos)",
    cover_wall_maintained: "Interruptor o conmutador subir/0/bajar (se queda puesto)",
    cover_wall_one: "Entrada del botón",
    cover_wall_up: "Entrada del botón de subir",
    cover_wall_down: "Entrada del botón de bajar (opcional)",
    cover_wall_one_help: "Un pulsador: cada pulsación da un paso: subir → parar → bajar → parar.",
    cover_wall_one_maintained_help: "Un interruptor: cada cambio de posición da un paso: subir → parar → bajar → parar.",
    cover_wall_two_help: "Dos pulsadores: uno sube y otro baja; cualquier pulsación mientras se mueve la para.",
    cover_wall_two_maintained_help: "Conmutador subir/0/bajar: sube o baja mientras está puesto y se para al volver al centro.",
    cover_meter_help: "Opcional. Un sensor de consumo (W) del motor, o una entidad encendido/apagado que diga si se mueve. En una subida o bajada completa, la persiana se da por llegada cuando el motor se para en su final de carrera, no cuando pasa el tiempo: así 0 % y 100 % se corrigen solos. Si se mueve con el mando original, el atributo position_reliable pasa a false hasta el siguiente recorrido completo.",
    cover_threshold: "El motor está en marcha por encima de (W)",
    measure_title: "Cronometrar el recorrido",
    measure_open: "Cronometrar subida",
    measure_close: "Cronometrar bajada",
    measure_help: "Para la subida, deja antes la persiana bajada del todo (y al revés para la bajada). Al pulsar se envía la orden y empieza a contar; pulsa «Ha llegado» cuando termine el recorrido. El tiempo se guarda arriba y puedes retocarlo a mano para el ajuste fino.",
    measure_save_first: "Guarda el dispositivo con los botones Subir y Bajar aprendidos para poder cronometrar el recorrido.",
    measure_opening: "Subiendo…",
    measure_closing: "Bajando…",
    measure_arrived: "Ha llegado",
    measure_cancel: "Cancelar",
    measure_running: "Pulsa «Ha llegado» en el momento en que la persiana termine el recorrido.",
    measure_running_meter: "Se parará solo cuando el medidor vea que el motor se detiene; también puedes pulsar «Ha llegado».",
    device_class: "Clase",
    speeds: "Velocidades",
    fan_light: "Luz del ventilador",
    fan_power: "Encendido del ventilador",
    power_off_button: "Botón de apagar",
    power_toggle: "Un botón que enciende y apaga",
    direction: "Sentido de giro",
    dir_toggle: "Un botón que invierte el giro",
    dir_buttons: "Botones verano / invierno",
    presets: "Modos especiales (separados por comas)",
    presets_help: "Por ejemplo: Brisa. Cada modo tendrá su botón que capturar.",
    feedback: "Estado real (opcional)",
    feedback_help: "Un sensor de consumo (W) o una entidad encendido/apagado que diga si de verdad está encendido. Así el estado es correcto aunque se use el mando original.",
    light_feedback: "Estado real de la luz (opcional)",
    threshold: "Encendido por encima de (W)",
    hold: "Mantener pulsado (s)",
    tab_general: "General",
    tab_buttons: "Botones del mando",
    tab_light: "Luz",
    tab_relay: "Relé y pared",
    tab_power: "Consumo",
    tab_live: "Probar",
    live_title: "Probar en vivo",
    live_rf: "Dispositivo RF",
    live_relay_group: "Relé e interruptor",
    live_save_first: "Guarda el dispositivo para probarlo aquí.",
    live_reloading: "Recargando entidades…",
    st_saved: "Guardado",
    st_saving: "Guardando…",
    st_dirty: "Cambios sin guardar",
    st_error: "Error al guardar",
    create: "Crear dispositivo",
    take_relay_name: "Usar el nombre del relé para la luz",
    take_relay_name_help: "La luz de RF Devices pasa a llamarse como el relé (el nombre que ya usáis por voz) y el relé se renombra «Interruptor …». Al desmarcarlo vuelve todo como estaba.",
    take_relay_entity_id: "Tomar también su identificador (entity_id)",
    take_relay_entity_id_help: "Alexa, las rutinas y los paneles reconocen los dispositivos por su entity_id, no por el nombre. Con esto, lo que antes controlaba el relé (p. ej. «Alexa, apaga la luz de la terraza») pasa a controlar la luz de RF Devices; el relé pasa a «…interruptor_…». Reversible.",
    wall_state: "Pulsador de pared",
    relay_state: "Relé",
    meter_state: "Consumo",
    on_word: "Encendido",
    off_word: "Apagado",
    press: "Pulsar",
    speed_word: "Velocidad",
    forward: "Verano",
    reverse: "Invierno",
    brightness: "Brillo",
    live_badge: "en directo",
    sync_no_send: "Ajustar sin enviar",
    sync_no_send_help: "Marca el modo en que está la lámpara ahora; no se transmite nada.",
    relay_title: "Relé e interruptor de pared",
    relay_q: "¿Está conectado a un relé o a un interruptor de pared?",
    relay_no: "No, siempre tiene corriente",
    relay_yes: "Sí, un relé (Shelly, Sonoff, Tuya…) le da corriente",
    relay_wall_only: "Solo un interruptor de pared: siempre tiene corriente",
    wall_only_help: "El dispositivo siempre tiene corriente. El interruptor de pared (por ejemplo, la entrada de un Shelly desacoplado cuya salida no está conectada) solo se usa para leer las pulsaciones: cada cambio alterna la luz por radio.",
    has_light: "Tiene luz",
    relay_entity: "Relé que le da corriente",
    relay_detected: "Detectado: {label}",
    relay_mode: "Cómo funciona el interruptor de pared",
    mode_a: "A · Acoplado: el interruptor corta y da la corriente",
    mode_b: "B · Desacoplado: el interruptor lo gestiona Home Assistant",
    mode_a_help: "El interruptor de pared actúa directamente sobre el relé, sin pasar por Home Assistant. Al darle corriente se enciende la luz; al quitarla se apaga todo. Si pides encender la luz con el relé apagado, RF Devices enciende el relé.",
    mode_b_help: "El interruptor ya no mueve el relé: Home Assistant lo lee y RF Devices enciende o apaga la luz por radio. El relé queda encendido y el ventilador siempre se puede usar. Si Home Assistant no está disponible, el interruptor no hace nada salvo que actives el script de emergencia.",
    wall_input: "Entrada del interruptor de pared",
    wall_input_disabled: "Esta entidad está desactivada en Home Assistant: se activará al pulsar «Aplicar al relé».",
    meter_entity: "Medidor de consumo",
    fan_power_on: "Permitir dar corriente para encender el ventilador",
    fan_power_on_help: "Con el relé apagado, encender el ventilador obliga a dar corriente: la luz se encenderá uno o dos segundos y RF Devices la apagará. Desactivado, el ventilador se niega a encender sin corriente (recomendado en dormitorios).",
    command_interval: "Pausa entre órdenes (s)",
    command_interval_help: "Tiempo mínimo entre dos envíos cualesquiera a este dispositivo. Vacío = el valor general de la integración ({g} s). El arranque sin corriente tiene sus propios tiempos (pestaña Relé y pared).",
    tl_relay: "Relé ON",
    turn_on_speed: "Velocidad al encender sin indicar velocidad",
    turn_on_last: "La última usada",
    turn_on_speed_help: "Se envía el código de esa velocidad (no el botón de encendido), así siempre sabemos en qué velocidad arranca.",
    pct_title: "Porcentajes ↔ velocidades (Home Assistant y Alexa)",
    pct_help: "Alexa y Home Assistant piden el ventilador en porcentaje. Cada velocidad cubre hasta el porcentaje indicado, que es también el que se muestra.",
    pct_small: "Un número pequeño es la velocidad (p. ej. «pon el ventilador al 2» = velocidad 2)",
    pct_reset: "Reparto uniforme",
    cal_up: "subiendo",
    cal_down: "bajando",
    cal_range: "rango",
    cal_band: "Umbral para reconocer una velocidad",
    cal_band_help: "Una lectura cuenta como una velocidad si está a menos de ± este margen (el mayor de los dos) y claramente más cerca de ella que de la siguiente. El PWM y la temperatura hacen que oscile.",
    cal_steps: "Salto al pulsar el botón de color",
    cal_steps_help: "Con esto se reconoce un cambio de color hecho con el mando original, aunque la lámpara se caliente y gaste algo menos. Los saltos de menos de 0,5 W no se pueden ver.",
    tl_light_off: "Apagar luz (RF)",
    tl_fan: "Orden del ventilador (RF)",
    tl_title: "Arranque del ventilador sin corriente",
    power_up_delay: "Espera tras dar corriente (s)",
    power_up_delay_help: "Tiempo que se deja al receptor del ventilador para arrancar antes de apagar la luz y enviar la orden. Si a veces no obedece, súbelo.",
    power_up_wait_meter: "Terminar la espera en cuanto el medidor vea la luz",
    power_up_gap: "Pausa entre apagar la luz y la orden del ventilador (s)",
    power_up_check: "Comprobar que la luz se ha apagado y, si no, repetir la orden",
    power_up_check_help: "A los 2 s mira el medidor; si aún ve la luz (y nadie la ha pedido), vuelve a enviar el apagado. Hasta 2 veces.",
    color_power_up: "Al recibir corriente, la temperatura de color…",
    cpu_memory: "…se mantiene (tiene memoria)",
    cpu_fixed: "…vuelve siempre a un modo fijo",
    cpu_quick: "…avanza al siguiente si el corte es rápido (menos de 3 s)",
    color_start_fixed: "Modo fijo al recibir corriente",
    ensure_light_on: "Encender siempre la luz al dar corriente",
    ensure_light_on_help: "Al encender el relé (pared, voz o HA) la luz debe encenderse. Si la lámpara tiene memoria y se queda apagada, RF Devices lo ve en el consumo y le envía la orden de encender. No actúa cuando se da corriente para arrancar el ventilador.",
    stale_reloaded: "Este dispositivo se había cambiado desde otro sitio: se ha cargado la versión actual. Repite tu último cambio.",
    gestures_title: "Gestos del interruptor de pared",
    gestures_help: "Cambios seguidos del interruptor (cada uno a menos de la ventana del anterior). Si solo 1 cambio tiene acción, responde al instante; si no, espera la ventana tras el último cambio. Cada gesto se publica también como evento rf_devices_wall_gesture para automatizaciones. La confirmación al script del Shelly se envía en el primer cambio.",
    gesture_n: "{n} cambio(s)",
    gesture_4: "4 o más cambios",
    gesture_window: "Ventana entre cambios (s)",
    ga_none: "Nada",
    ga_light_toggle: "Alternar luz",
    ga_light_on: "Encender luz",
    ga_light_off: "Apagar luz",
    ga_light_color: "Siguiente color de luz",
    ga_fan_step: "Ventilador: encender o subir (en la máxima, baja)",
    ga_fan_up: "Ventilador: encender o subir",
    ga_fan_down: "Ventilador: bajar velocidad",
    ga_fan_toggle: "Ventilador: encender/apagar",
    ga_fan_on: "Encender ventilador",
    ga_fan_off: "Apagar ventilador",
    ga_fan_direction: "Cambiar sentido de giro",
    ga_all_off: "Apagar todo (luz y ventilador por RF)",
    ga_power_off: "Cortar el relé",
    fallback_script: "Script de emergencia en el Shelly",
    fallback_help: "Cada pulsación de la pared la confirma Home Assistant al Shelly en unas décimas de segundo. Si no llega la confirmación en el tiempo indicado (HA caído, reiniciando o colgado), el propio Shelly conmuta el relé, como en el modo A. No usa tráfico ni escribe en la memoria del Shelly mientras no se pulsa.",
    fallback_wait: "Espera de la confirmación (s)",
    hide_sources: "Ocultar las entidades del relé (siguen funcionando)",
    hide_help: "Las entidades del relé y del interruptor se ocultan de paneles y listas para que la luz y el ventilador de RF Devices sean los únicos visibles. Si ya las usan Alexa o automatizaciones, revisa esas referencias.",
    idle_title: "Apagar el relé tras un tiempo con todo apagado",
    idle_minutes: "Minutos con luz y ventilador apagados (0 = nunca)",
    idle_when: "Cuándo",
    idle_always: "Siempre",
    idle_night: "Solo de noche (sol bajo el horizonte)",
    idle_hours: "Solo en una franja horaria",
    idle_from: "Desde",
    idle_to: "Hasta",
    idle_help: "Un relé tiene los contactos pensados para estar normalmente abiertos. Mantenerlo cerrado de forma permanente durante años los fatiga y pueden quedarse pegados (el relé deja de apagar). Apagarlo cuando no se usa alarga su vida. Contrapartida: la próxima vez que se encienda el ventilador habrá que dar corriente (ver opción anterior).",
    apply_relay: "Aplicar al relé",
    apply_confirm: "Se configurará el relé para el modo elegido (desacoplar o acoplar el interruptor, instalar o quitar el script, activar la entrada). ¿Continuar?",
    applied: "Hecho: {list}",
    nothing_to_apply: "El relé ya estaba configurado así.",
    save_first_relay: "Guarda el dispositivo antes de aplicar la configuración al relé.",
    note_detach_in_vendor_app: "Este relé se controla con sus entidades de Home Assistant. Si quieres el modo B, desacopla el interruptor en la app del fabricante (si lo permite).",
    note_shelly_password: "Shelly con contraseña: por ahora solo se usan sus entidades de Home Assistant.",
    d_wall: "Interruptor",
    d_relay: "Relé",
    d_meter: "Medidor",
    d_fan: "Ventilador + luz",
    d_light: "Luz",
    d_rf: "Emisor RF",
    color_kelvin: "Temperatura de cada modo (K)",
    color_kelvin_help: "Para regular la temperatura desde Home Assistant o Alexa. Por ejemplo: 6000, 4000, 2700.",
    dim_time: "Segundos manteniendo pulsado de mínimo a máximo brillo",
    frames_label: "Tramas",
    frames_help: "Cuántas repeticiones de la trama se envían. Si al probar el botón se activa dos veces (p. ej. enciende y apaga), prueba con menos; si a veces no responde, con más.",
    timers: "Temporizadores (separados por comas)",
    timers_help: "Por ejemplo: 1H, 2H, 4H, 8H. Cada uno será un botón.",
    light_name: "Nombre de la luz",
    light_color: "Tiene botón de temperatura de color",
    light_dim: "Tiene botones de subir y bajar brillo",
    r_timer: "Temporizador {label}",
    r_light_color: "Color de la luz",
    r_light_up: "Subir luz",
    r_light_down: "Bajar luz",
    copy_code: "Copiar código",
    copied: "Código copiado",
    from_device: "Desde otro dispositivo",
    code_title: "Código de «{role}»",
    devices_title: "Códigos de tus otros dispositivos",
    calibrate: "Calibrar consumo",
    calibrate_light: "Calibrar solo la luz (1–2 min)",
    calibrate_light_help: "La calibración rápida mide la lámpara con el ventilador parado. Basta para distinguir la luz del ventilador por los saltos de consumo; la completa, además, reconoce cada velocidad.",
    calibrate_light_intro: "Se mide el consumo en reposo y el de la lámpara en cada modo de color, con el ventilador parado. La luz se encenderá, cambiará de color y se apagará.",
    calibrate_light_before: "Antes de empezar, apaga el ventilador y la luz con el mando. Tarda 1–2 minutos.",
    cal_light_done: "Listo. Guárdalo para que la luz siga al consumo (si ya tienes la calibración completa, se actualizan sus valores de la lámpara).",
    cal_light_table: "Luz calibrada ({date})",
    calibrate_title: "Calibrar el consumo del ventilador",
    calibrate_intro: "Se medirá el reposo, la luz (en cada modo de color) y cada velocidad subiendo y después bajando, esperando a que el motor se estabilice (un par de minutos por paso: un motor con PWM gasta distinto al llegar a una velocidad desde abajo que desde arriba). Con esa tabla, RF Devices corregirá solo el estado del ventilador y de la luz cuando se use el mando original.",
    calibrate_before: "Antes de empezar: apaga el ventilador y la luz con el mando y no los toques hasta que termine. Tardará unos {min} minutos.",
    calibrate_save_first: "Guarda el dispositivo antes de calibrar.",
    calibrate_need_meter: "Elige antes el medidor de consumo (estado real de la luz).",
    cal_direct: "Leyendo el medidor en directo (cada segundo, con decimales).",
    cal_pushed: "El medidor no admite lectura directa: se usan los valores que publica en Home Assistant, más lentos.",
    cal_idle: "Reposo",
    cal_light: "Solo luz",
    cal_mode: "modo de color {n}",
    light_colors: "Modos de color que recorre el botón",
    color_names: "Nombres de los modos, en el orden del botón",
    color_names_help: "Por ejemplo: Frío, Neutro, Cálido. Aparecerá un selector «Temperatura de color» que envía las pulsaciones necesarias.",
    cal_edit_help: "Puedes corregir cualquier valor a mano; se guarda con el dispositivo.",
    cal_speed: "Velocidad {n}",
    cal_speed_wait: "Velocidad {n}: esperando a que se estabilice…",
    cal_light_on: "con luz",
    cal_took: "estable en {s} s",
    cal_unsettled: "no llegó a estabilizarse",
    cal_done: "Calibración terminada. Guárdala para activar el alineador automático.",
    cal_save: "Guardar calibración",
    cal_remove: "Borrar calibración",
    cal_table: "Calibración ({date})",
    cal_live: "Calibración en vivo: tras cada orden de velocidad, con la luz apagada, esperar a que el motor se estabilice de verdad (hasta 15 min) y corregir el valor de esa velocidad",
    cal_learned: "Corregido en vivo: {list}",
    cal_warn_close: "Hay velocidades con consumos muy parecidos ({list}): entre ellas solo se corregirá encendido/apagado.",
    live_meter: "Consumo",
    live_relay: "Relé",
    live_switch: "Pulsador",
    live_on: "encendido",
    live_off: "apagado",
    live_light_on: "luz encendida",
    live_light_off: "luz apagada",
    hold_help: "0 = pulsación corta. Para botones que actúan mientras se mantienen, como el brillo.",
    r_toggle: "Botón (alterna)",
    r_on: "Encender",
    r_off: "Apagar",
    r_open: "Subir / abrir",
    r_close: "Bajar / cerrar",
    r_stop: "Parar",
    r_speed: "Velocidad {n}",
    r_light_toggle: "Luz (alterna)",
    r_light_on: "Encender luz",
    r_light_off: "Apagar luz",
    r_power: "Encender / apagar",
    r_direction: "Invertir giro",
    r_forward: "Verano",
    r_reverse: "Invierno",
    optional: "opcional",
    not_learned: "Sin capturar",
    learn: "Capturar",
    test: "Probar",
    more: "Más",
    paste: "Pegar código",
    from_broadlink: "Desde Broadlink",
    clean: "Limpiar",
    remove: "Quitar",
    sent: "Enviado",
    add_button: "Añadir botón",
    button_name: "Nombre del botón extra",
    needs_cleaning: "Captura sin limpiar: {frames} tramas, se envía {times} ({ms} ms). Pulsa Limpiar.",
    once: "1 vez",
    times: "{n} veces",
    duplicate: "Es el mismo código que «{other}».",
    frames_info: "{good} tramas · {ms} ms",
    missing: "Faltan: {list}",
    learn_title: "Capturar «{role}»",
    known_freq: "Usar la frecuencia ya conocida ({f} MHz): basta con una pulsación",
    capture_tip: "Acerca el mando a unos 10–20 cm del Broadlink. Primero se busca la señal manteniendo pulsado; después se pide una segunda pulsación.",
    start: "Empezar",
    capture_tip_rx: "Acerca el mando al receptor. Cuando se pida, pulsa el botón y mantenlo alrededor de un segundo.",
    st_starting: "Preparando el emisor…",
    st_sweep: "Mantén pulsado el botón «{role}» del mando cerca del Broadlink hasta que se detecte la frecuencia.",
    st_frequency: "Frecuencia detectada: {f} MHz. Suelta el botón.",
    st_found: "Señal detectada. Suelta el botón y espera.",
    st_press: "Ahora pulsa el botón «{role}» y mantenlo pulsado alrededor de un segundo. Después suéltalo y espera.",
    st_timeout: "No se ha recibido nada a tiempo.",
    st_error: "Error: {msg}",
    st_unreachable: "El Broadlink no responde, así que no se ha empezado a capturar. Espera unos segundos y repite; si sigue igual, desenchúfalo un momento.",
    retry: "Repetir",
    raw_capture: "Captura original",
    cleaned: "Versión limpia (recomendada)",
    use_clean: "Usar la limpia",
    use_raw: "Usar la original",
    test_clean: "Probar limpia",
    test_raw: "Probar original",
    summary: "{frames} tramas ({bad} incompletas) · se envía {times} · {ms} ms en total",
    paste_title: "Pegar código Broadlink (base64)",
    analyze: "Analizar",
    bl_title: "Códigos aprendidos con la integración Broadlink",
    bl_empty: "No hay códigos guardados por la integración Broadlink.",
    use: "Usar",
    import_done: "Importados {added}, sobrescritos {replaced}.",
    import_replace: "¿Sobrescribir los dispositivos que ya existan con el mismo identificador? (Cancelar = importarlos como copia)",
    no_learn: "Este emisor no puede aprender códigos: {msg}",
    st_unreachable_rx: "El receptor no responde, así que no se ha empezado a capturar. Comprueba que el dispositivo esté conectado a Home Assistant.",
    frequency: "{f} MHz",
    entities: "Entidades",
    control_title: "Cómo se controla",
    control_rf: "Códigos RF capturados (Broadlink, ESP32 + CC1101…)",
    control_somfy: "Somfy RTS generado (mando virtual)",
    control_linked: "Otra integración (ESPSomfy RTS, ble_adv, ESPHome…)",
    control_help: "Con códigos RF se captura cada botón del mando original. Somfy RTS cambia el código en cada pulsación, así que RF Devices hace de mando nuevo y hay que emparejarlo con el motor. Con otra integración, cada botón llama a una acción de Home Assistant y el estado se copia de su entidad.",
    somfy_address: "Dirección del mando virtual",
    somfy_new: "Nueva dirección",
    somfy_new_confirm: "Con una dirección nueva el motor deja de reconocer este mando hasta que lo vuelvas a emparejar. ¿Continuar?",
    somfy_invert: "El motor gira al revés (intercambiar subir y bajar)",
    somfy_repeats: "Repeticiones por pulsación",
    somfy_code: "Último código enviado: {n}",
    somfy_pair: "Emparejar (PROG)",
    somfy_pair_help: "1) En un mando que ya mueva la persiana, mantén pulsado PROG (detrás) hasta que la persiana suba y baje un poco. 2) Antes de 2 minutos, pulsa «Emparejar»: la persiana vuelve a moverse y el mando virtual queda emparejado. Repetir el proceso lo desempareja. Los motores admiten unos 12 mandos: no emparejes mandos de prueba sin necesidad y no pierdas el mando original.",
    somfy_pair_sent: "PROG enviado: la persiana debería moverse un poco.",
    somfy_note: "Aviso: {msg}",
    somfy_fill: "Asignar los botones Somfy",
    somfy_button: "Botón Somfy",
    somfy_needs_save: "Guarda el dispositivo antes de emparejar.",
    b_up: "Subir", b_down: "Bajar", b_my: "My / parar", b_my_up: "My + subir", b_my_down: "My + bajar",
    b_up_down: "Subir + bajar", b_prog: "PROG", b_sun_flag: "Sol", b_flag: "Bandera",
    kind_somfy: "Somfy · {b}",
    kind_action: "Acción · {svc}",
    more_action: "Acción de Home Assistant…",
    more_somfy: "Botón Somfy…",
    action_title: "Acción de Home Assistant — {role}",
    action_service: "Acción (servicio)",
    action_entity: "Entidad",
    action_data: "Datos adicionales (JSON, opcional)",
    action_help: "Por ejemplo: cover.open_cover sobre la persiana de ESPSomfy RTS, fan.set_percentage con {\"percentage\": 50} sobre un ventilador de ble_adv, o button.press sobre un botón de ESPHome.",
    action_bad_json: "Los datos adicionales no son un JSON válido.",
    action_bad_service: "Escribe la acción como dominio.servicio (p. ej. cover.open_cover).",
    linked_entity: "Entidad que controla el aparato",
    linked_light: "Entidad de la luz (si la integración la separa)",
    linked_help: "RF Devices llama a esta entidad y copia su estado: ESPSomfy RTS escucha los mandos y ble_adv recuerda lo que envía.",
    mirror: "Copiar su estado (recomendado)",
    linked_fill: "Rellenar los botones con sus acciones",
    linked_filled: "Botones rellenados con las acciones de {e}.",
    linked_none: "No hay entidades de otras integraciones de este tipo.",
    follow: "Seguir el mando original",
    follow_help: "El receptor escucha siempre: si alguien usa el mando de siempre, RF Devices actualiza el estado sin enviar nada. Cada pulsación reconocida lanza el evento rf_devices_remote (útil en automatizaciones, p. ej. para una alarma).",
    follow_problem: "No se puede escuchar con este emisor: {msg}",
    follow_somfy: "Mandos Somfy reales que se siguen",
    follow_somfy_none: "Ninguno todavía.",
    follow_somfy_detect: "Detectar un mando Somfy",
    follow_somfy_found: "Mando {hex} · botón {b} · código {c}",
    follow_somfy_add: "Seguir este mando",
    follow_somfy_nothing: "No se ha reconocido ninguna trama Somfy en la captura.",
    follow_somfy_title: "Detectar un mando Somfy",
    remove_short: "Quitar",
  },
  en: {
    title: "RF Devices",
    new_device: "New device",
    export: "Export",
    debug_report: "Diagnostics",
    debug_report_help: "Downloads a report for remote debugging: versions, transmitters, ESPHome devices, entities in use, latest transmissions and captures (with the bursts received) and log. No passwords or stored codes; it does include the bursts received during captures.",
    import: "Import",
    empty: "No devices yet. Create one and capture the buttons of its remote.",
    edit: "Edit",
    delete: "Delete",
    confirm_delete: "Delete “{name}” and its entities?",
    back: "Back",
    save: "Save",
    saved: "Saved. Entities are reloading…",
    close: "Close",
    name: "Name",
    type: "Type",
    transmitter: "RF transmitter",
    default_tx: "Default ({name})",
    device: "Device",
    buttons: "Remote buttons",
    t_light: "Light",
    t_switch: "Plug / switch",
    t_cover: "Blind / awning",
    t_fan: "Fan",
    t_fan_light: "Fan with light · one remote",
    group_fan: "Fan",
    group_light: "Light",
    ha_devices: "Devices in Home Assistant",
    open_device_help: "On the device page, «Add to dashboard» puts it on a dashboard.",
    t_buttons: "Buttons only",
    mode: "Remote",
    mode_toggle: "Single toggle button",
    mode_onoff: "Separate on and off buttons",
    switch_entity: "Wall switch (optional)",
    switch_entity_help: "Every change of this switch toggles the device, whatever its position. Handy with a detached Shelly input.",
    none: "None",
    open_time: "Opening time (s)",
    close_time: "Closing time (s)",
    times_help: "With both times the position is estimated and a percentage can be set (needs the Stop button).",
    cover_wiring_q: "Does it have a relay or wall buttons?",
    cover_wiring_none: "Nothing: the RF remote only",
    cover_wiring_wall: "Wall buttons only",
    cover_wiring_relay: "A relay powers it",
    cover_wiring_relay_wall: "A relay and wall buttons",
    cover_relay_intro: "All optional. Without any of this the cover works by time with the RF remote.",
    cover_relay_help: "Relay (Shelly, plug…) that powers the motor. Nothing is sent while the relay is off.",
    cover_power_on: "Switch the relay on when needed to move the cover",
    cover_power_up_delay_help: "Time given to the motor's receiver to start before the command is sent.",
    cover_wall_type: "Kind of buttons",
    cover_wall_momentary: "Push buttons (spring back)",
    cover_wall_maintained: "Switch or up/0/down rocker (stays put)",
    cover_wall_one: "Button input",
    cover_wall_up: "Up button input",
    cover_wall_down: "Down button input (optional)",
    cover_wall_one_help: "One push button: every press is one step: open → stop → close → stop.",
    cover_wall_one_maintained_help: "One switch: every change of position is one step: open → stop → close → stop.",
    cover_wall_two_help: "Two push buttons: one opens, the other closes; any press while it moves stops it.",
    cover_wall_two_maintained_help: "Up/0/down rocker: it opens or closes while held in place and stops when back at the centre.",
    cover_meter_help: "Optional. A power sensor (W) of the motor, or an on/off entity telling whether it moves. On a full opening or closing the cover arrives when the motor stops at its limit switch, not when the time is up, so 0 % and 100 % correct themselves. If the original remote moves it, the position_reliable attribute turns false until the next full travel.",
    cover_threshold: "The motor is running above (W)",
    measure_title: "Time the travel",
    measure_open: "Time the opening",
    measure_close: "Time the closing",
    measure_help: "For the opening, leave the cover fully closed first (and the other way round for the closing). Pressing sends the command and starts the clock; press “It has arrived” when the travel ends. The time is stored above and can be fine-tuned by hand.",
    measure_save_first: "Save the device with the Open and Close buttons learned to time the travel.",
    measure_opening: "Opening…",
    measure_closing: "Closing…",
    measure_arrived: "It has arrived",
    measure_cancel: "Cancel",
    measure_running: "Press “It has arrived” the moment the cover ends its travel.",
    measure_running_meter: "It stops by itself when the meter sees the motor stop; you can also press “It has arrived”.",
    device_class: "Class",
    speeds: "Speeds",
    fan_light: "Fan light",
    fan_power: "Fan power",
    power_off_button: "Off button",
    power_toggle: "One on/off button",
    direction: "Direction",
    dir_toggle: "One button reverses",
    dir_buttons: "Summer / winter buttons",
    presets: "Special modes (comma separated)",
    presets_help: "E.g. Breeze. Each mode gets a button to capture.",
    feedback: "Real state (optional)",
    feedback_help: "A power sensor (W) or an on/off entity telling whether it is really on, so the state stays right even when the original remote is used.",
    light_feedback: "Real state of the light (optional)",
    threshold: "On above (W)",
    hold: "Hold (s)",
    tab_general: "General",
    tab_buttons: "Remote buttons",
    tab_light: "Light",
    tab_relay: "Relay & wall",
    tab_power: "Power",
    tab_live: "Test",
    live_title: "Live test",
    live_rf: "RF device",
    live_relay_group: "Relay & switch",
    live_save_first: "Save the device to test it here.",
    live_reloading: "Reloading entities…",
    st_saved: "Saved",
    st_saving: "Saving…",
    st_dirty: "Unsaved changes",
    st_error: "Save failed",
    create: "Create device",
    take_relay_name: "Use the relay's name for the light",
    take_relay_name_help: "The RF Devices light takes the relay's name (the one already used by voice) and the relay is renamed “Switch …”. Unticking puts everything back.",
    take_relay_entity_id: "Also take its identifier (entity_id)",
    take_relay_entity_id_help: "Alexa, routines and dashboards know devices by entity_id, not by name. With this, whatever controlled the relay (e.g. “Alexa, turn off the terrace light”) now controls the RF Devices light; the relay becomes “…switch_…”. Reversible.",
    wall_state: "Wall switch",
    relay_state: "Relay",
    meter_state: "Power",
    on_word: "On",
    off_word: "Off",
    press: "Press",
    speed_word: "Speed",
    forward: "Summer",
    reverse: "Winter",
    brightness: "Brightness",
    live_badge: "live",
    sync_no_send: "Adjust without sending",
    sync_no_send_help: "Mark the mode the lamp is in now; nothing is transmitted.",
    relay_title: "Relay and wall switch",
    relay_q: "Is it wired to a relay or a wall switch?",
    relay_no: "No, it is always powered",
    relay_yes: "Yes, a relay (Shelly, Sonoff, Tuya…) powers it",
    relay_wall_only: "Only a wall switch: it is always powered",
    wall_only_help: "The device is always powered. The wall switch (e.g. a detached Shelly input whose output is not wired) is only read: every change toggles the light by radio.",
    has_light: "Has a light",
    relay_entity: "Relay powering it",
    relay_detected: "Detected: {label}",
    relay_mode: "How the wall switch works",
    mode_a: "A · Coupled: the switch cuts and restores power",
    mode_b: "B · Detached: Home Assistant handles the switch",
    mode_a_help: "The wall switch drives the relay directly, without Home Assistant. Powering it lights the lamp; cutting it switches everything off. Asking for the light with the relay off switches the relay on.",
    mode_b_help: "The switch no longer moves the relay: Home Assistant reads it and RF Devices toggles the light by radio. The relay stays on, so the fan can always be used. If Home Assistant is down the switch does nothing unless the fallback script is enabled.",
    wall_input: "Wall switch input",
    wall_input_disabled: "This entity is disabled in Home Assistant: it will be enabled by “Apply to relay”.",
    meter_entity: "Power meter",
    fan_power_on: "Allow powering the relay to start the fan",
    fan_power_on_help: "With the relay off, starting the fan means powering it: the light comes on for a second or two and RF Devices switches it off. When disabled the fan refuses to start without power (recommended in bedrooms).",
    command_interval: "Pause between commands (s)",
    command_interval_help: "Minimum time between any two transmissions to this device. Empty = the integration's default ({g} s). Starting without power has its own timings (Relay & wall tab).",
    tl_relay: "Relay ON",
    turn_on_speed: "Speed when turned on without a speed",
    turn_on_last: "The last one used",
    turn_on_speed_help: "That speed's code is sent (not the power button), so the starting speed is always known.",
    pct_title: "Percentages ↔ speeds (Home Assistant and Alexa)",
    pct_help: "Alexa and Home Assistant ask for the fan in percent. Each speed covers up to the percentage given, which is also the one shown.",
    pct_small: "A small number is the speed (e.g. “set the fan to 2” = speed 2)",
    pct_reset: "Even split",
    cal_up: "going up",
    cal_down: "going down",
    cal_range: "range",
    cal_band: "Band to recognise a speed",
    cal_band_help: "A reading counts as a speed if it is within ± this margin (the larger of the two) and clearly nearer to it than to the next one. PWM and temperature make it wander.",
    cal_steps: "Jump when the colour button is pressed",
    cal_steps_help: "This recognises a colour change made with the original remote, even when the lamp warms up and draws a little less. Jumps under 0.5 W cannot be seen.",
    tl_light_off: "Light off (RF)",
    tl_fan: "Fan command (RF)",
    tl_title: "Starting the fan without power",
    power_up_delay: "Wait after powering (s)",
    power_up_delay_help: "Time given to the fan's receiver to start before switching the light off and sending the command. Raise it if it sometimes ignores the command.",
    power_up_wait_meter: "End the wait as soon as the meter sees the light",
    power_up_gap: "Pause between light off and the fan command (s)",
    power_up_check: "Check the light went off and repeat the command if not",
    power_up_check_help: "After 2 s it looks at the meter; if it still sees the light (and nobody asked for it) it sends “off” again. Up to twice.",
    color_power_up: "When it gets power, the colour temperature…",
    cpu_memory: "…stays as it was (it has memory)",
    cpu_fixed: "…always returns to a fixed mode",
    cpu_quick: "…moves to the next one on a quick cut (under 3 s)",
    color_start_fixed: "Fixed mode when it gets power",
    ensure_light_on: "Always switch the light on when power returns",
    ensure_light_on_help: "When the relay powers up (wall, voice or HA) the light should come on. If the lamp has memory and stays off, RF Devices sees it on the meter and sends “on”. Not done when power is given to start the fan.",
    stale_reloaded: "This device was changed elsewhere: the current version was loaded. Repeat your last change.",
    gestures_title: "Wall switch gestures",
    gestures_help: "Quick flips of the switch (each within the window of the previous one). If only 1 flip has an action it responds at once; otherwise it waits for the window after the last flip. Every gesture is also fired as the rf_devices_wall_gesture event for automations. The fallback script is confirmed on the first flip.",
    gesture_n: "{n} flip(s)",
    gesture_4: "4 or more flips",
    gesture_window: "Window between flips (s)",
    ga_none: "Nothing",
    ga_light_toggle: "Toggle light",
    ga_light_on: "Light on",
    ga_light_off: "Light off",
    ga_light_color: "Next light colour",
    ga_fan_step: "Fan: on or faster (from the top, slower)",
    ga_fan_up: "Fan: on or faster",
    ga_fan_down: "Fan: slower",
    ga_fan_toggle: "Fan: on/off",
    ga_fan_on: "Fan on",
    ga_fan_off: "Fan off",
    ga_fan_direction: "Reverse direction",
    ga_all_off: "Everything off (light and fan by RF)",
    ga_power_off: "Cut the relay",
    fallback_script: "Fallback script on the Shelly",
    fallback_help: "Home Assistant confirms every wall-switch press to the Shelly within tenths of a second. If no confirmation arrives in time (HA down, restarting or hung), the Shelly itself toggles the relay, as in mode A. No traffic and no writes to the Shelly's memory while nobody presses.",
    fallback_wait: "Wait for the confirmation (s)",
    hide_sources: "Hide the relay's entities (they keep working)",
    hide_help: "The relay and switch entities are hidden from dashboards and pickers so the RF Devices light and fan are the only ones shown. If Alexa or automations use them, check those references.",
    idle_title: "Switch the relay off after a while with everything off",
    idle_minutes: "Minutes with light and fan off (0 = never)",
    idle_when: "When",
    idle_always: "Always",
    idle_night: "Only at night (sun below the horizon)",
    idle_hours: "Only within a time window",
    idle_from: "From",
    idle_to: "To",
    idle_help: "A relay's contacts are meant to be normally open. Keeping them closed for years fatigues them and they can weld (the relay no longer switches off). Switching it off when unused extends its life. Trade-off: the next time the fan is started the relay must be powered (see the option above).",
    apply_relay: "Apply to relay",
    apply_confirm: "The relay will be configured for the chosen mode (detach or attach the switch, install or remove the script, enable the input). Continue?",
    applied: "Done: {list}",
    nothing_to_apply: "The relay was already set up like that.",
    save_first_relay: "Save the device before applying the configuration to the relay.",
    note_detach_in_vendor_app: "This relay is used through its Home Assistant entities. For mode B, detach the switch in the vendor's app (if it allows it).",
    note_shelly_password: "Password-protected Shelly: only its Home Assistant entities are used for now.",
    d_wall: "Wall switch",
    d_relay: "Relay",
    d_meter: "Meter",
    d_fan: "Fan + light",
    d_light: "Light",
    d_rf: "RF transmitter",
    color_kelvin: "Colour temperature of each mode (K)",
    color_kelvin_help: "To set the temperature from Home Assistant or Alexa. E.g. 6000, 4000, 2700.",
    dim_time: "Seconds held from minimum to maximum brightness",
    frames_label: "Frames",
    frames_help: "How many repetitions of the frame are sent. If testing triggers twice (e.g. on then off), try fewer; if it sometimes does not respond, try more.",
    timers: "Timers (comma separated)",
    timers_help: "E.g. 1H, 2H, 4H, 8H. Each one becomes a button.",
    light_name: "Light name",
    light_color: "Has a colour temperature button",
    light_dim: "Has brighter / dimmer buttons",
    r_timer: "Timer {label}",
    r_light_color: "Light colour",
    r_light_up: "Brighter",
    r_light_down: "Dimmer",
    copy_code: "Copy code",
    copied: "Code copied",
    from_device: "From another device",
    code_title: "Code of “{role}”",
    devices_title: "Codes of your other devices",
    calibrate: "Calibrate power",
    calibrate_light: "Calibrate the light only (1–2 min)",
    calibrate_light_help: "The quick calibration measures the lamp with the fan stopped. That is enough to tell the light from the fan by its jumps in draw; the full one also recognises each speed.",
    calibrate_light_intro: "Idle and the lamp in each colour mode are measured with the fan stopped. The light will turn on, change colour and turn off.",
    calibrate_light_before: "Before starting, switch the fan and the light off with the remote. It takes 1–2 minutes.",
    cal_light_done: "Done. Save it so the light follows the meter (with a full calibration, its lamp values are updated).",
    cal_light_table: "Light calibrated ({date})",
    calibrate_title: "Calibrate the fan's power draw",
    calibrate_intro: "Idle, the light (in each colour mode) and every speed going up and then going down are measured, waiting for the motor to settle (a couple of minutes per step: a PWM motor draws differently when it reaches a speed from below than from above). With that table RF Devices corrects the fan and light state by itself when the original remote is used.",
    calibrate_before: "Before starting: switch the fan and its light off with the remote and leave them until it finishes. It takes about {min} minutes.",
    calibrate_save_first: "Save the device before calibrating.",
    calibrate_need_meter: "Choose the power meter first (real state of the light).",
    cal_direct: "Reading the meter live (every second, with decimals).",
    cal_pushed: "The meter cannot be read live: using the values it publishes to Home Assistant, which are slower.",
    cal_idle: "Idle",
    cal_light: "Light only",
    cal_mode: "colour mode {n}",
    light_colors: "Colour modes the button cycles through",
    color_names: "Mode names, in the button's order",
    color_names_help: "E.g. Cold, Neutral, Warm. A “Colour temperature” selector will send the presses needed.",
    cal_edit_help: "Any value can be corrected by hand; it is saved with the device.",
    cal_speed: "Speed {n}",
    cal_speed_wait: "Speed {n}: waiting for it to settle…",
    cal_light_on: "light on",
    cal_took: "settled in {s} s",
    cal_unsettled: "did not settle",
    cal_done: "Calibration finished. Save it to enable automatic alignment.",
    cal_save: "Save calibration",
    cal_remove: "Remove calibration",
    cal_table: "Calibration ({date})",
    cal_live: "Live calibration: after each speed command, with the light off, wait until the motor has really settled (up to 15 min) and correct that speed's value",
    cal_learned: "Corrected live: {list}",
    cal_warn_close: "Some speeds draw almost the same ({list}): between them only on/off is corrected.",
    live_meter: "Power",
    live_relay: "Relay",
    live_switch: "Wall switch",
    live_on: "on",
    live_off: "off",
    live_light_on: "light on",
    live_light_off: "light off",
    hold_help: "0 = short press. For buttons that act while held, such as brightness.",
    r_toggle: "Button (toggle)",
    r_on: "On",
    r_off: "Off",
    r_open: "Up / open",
    r_close: "Down / close",
    r_stop: "Stop",
    r_speed: "Speed {n}",
    r_light_toggle: "Light (toggle)",
    r_light_on: "Light on",
    r_light_off: "Light off",
    r_power: "On / off",
    r_direction: "Reverse direction",
    r_forward: "Summer",
    r_reverse: "Winter",
    optional: "optional",
    not_learned: "Not captured",
    learn: "Capture",
    test: "Test",
    more: "More",
    paste: "Paste code",
    from_broadlink: "From Broadlink",
    clean: "Clean",
    remove: "Remove",
    sent: "Sent",
    add_button: "Add button",
    button_name: "Extra button name",
    needs_cleaning: "Uncleaned capture: {frames} frames, sent {times} ({ms} ms). Press Clean.",
    once: "once",
    times: "{n} times",
    duplicate: "Same code as “{other}”.",
    frames_info: "{good} frames · {ms} ms",
    missing: "Missing: {list}",
    learn_title: "Capture “{role}”",
    known_freq: "Use the known frequency ({f} MHz): a single press is enough",
    capture_tip: "Hold the remote 10–20 cm from the Broadlink. First the signal is found while you hold the button; then a second press is asked for.",
    start: "Start",
    capture_tip_rx: "Hold the remote close to the receiver. When asked, press the button and keep it pressed for about a second.",
    st_starting: "Preparing the transmitter…",
    st_sweep: "Press and hold the “{role}” button close to the Broadlink until the frequency is found.",
    st_frequency: "Frequency found: {f} MHz. Release the button.",
    st_found: "Signal found. Release the button and wait.",
    st_press: "Now press the “{role}” button and hold it for about a second. Then release it and wait.",
    st_timeout: "Nothing was received in time.",
    st_error: "Error: {msg}",
    st_unreachable: "The Broadlink is not answering, so capturing did not start. Wait a few seconds and retry; if it persists, unplug it for a moment.",
    retry: "Retry",
    raw_capture: "Original capture",
    cleaned: "Cleaned version (recommended)",
    use_clean: "Use cleaned",
    use_raw: "Use original",
    test_clean: "Test cleaned",
    test_raw: "Test original",
    summary: "{frames} frames ({bad} incomplete) · sent {times} · {ms} ms in total",
    paste_title: "Paste a Broadlink code (base64)",
    analyze: "Analyse",
    bl_title: "Codes learned with the Broadlink integration",
    bl_empty: "The Broadlink integration has no stored codes.",
    use: "Use",
    import_done: "Imported {added}, overwritten {replaced}.",
    import_replace: "Overwrite devices that already exist with the same id? (Cancel = import them as copies)",
    no_learn: "This transmitter cannot learn codes: {msg}",
    st_unreachable_rx: "The receiver is not answering, so capturing did not start. Check that the device is connected to Home Assistant.",
    frequency: "{f} MHz",
    entities: "Entities",
    control_title: "How it is controlled",
    control_rf: "Captured RF codes (Broadlink, ESP32 + CC1101…)",
    control_somfy: "Generated Somfy RTS (virtual remote)",
    control_linked: "Another integration (ESPSomfy RTS, ble_adv, ESPHome…)",
    control_help: "With RF codes each button of the original remote is captured. Somfy RTS changes its code on every press, so RF Devices acts as a new remote that must be paired with the motor. With another integration each button calls a Home Assistant action and the state is copied from its entity.",
    somfy_address: "Virtual remote address",
    somfy_new: "New address",
    somfy_new_confirm: "With a new address the motor stops recognising this remote until you pair it again. Continue?",
    somfy_invert: "The motor turns the other way (swap up and down)",
    somfy_repeats: "Repeats per press",
    somfy_code: "Last code sent: {n}",
    somfy_pair: "Pair (PROG)",
    somfy_pair_help: "1) On a remote that already moves the blind, hold PROG (at the back) until the blind jogs up and down. 2) Within 2 minutes, press “Pair”: the blind jogs again and the virtual remote is paired. Doing it again unpairs it. Motors accept about 12 remotes: do not pair test remotes needlessly, and keep the original remote.",
    somfy_pair_sent: "PROG sent: the blind should jog a little.",
    somfy_note: "Warning: {msg}",
    somfy_fill: "Assign the Somfy buttons",
    somfy_button: "Somfy button",
    somfy_needs_save: "Save the device before pairing.",
    b_up: "Up", b_down: "Down", b_my: "My / stop", b_my_up: "My + up", b_my_down: "My + down",
    b_up_down: "Up + down", b_prog: "PROG", b_sun_flag: "Sun", b_flag: "Flag",
    kind_somfy: "Somfy · {b}",
    kind_action: "Action · {svc}",
    more_action: "Home Assistant action…",
    more_somfy: "Somfy button…",
    action_title: "Home Assistant action — {role}",
    action_service: "Action (service)",
    action_entity: "Entity",
    action_data: "Extra data (JSON, optional)",
    action_help: "For example: cover.open_cover on an ESPSomfy RTS blind, fan.set_percentage with {\"percentage\": 50} on a ble_adv fan, or button.press on an ESPHome button.",
    action_bad_json: "The extra data is not valid JSON.",
    action_bad_service: "Write the action as domain.service (e.g. cover.open_cover).",
    linked_entity: "Entity that drives the device",
    linked_light: "Light entity (if the integration keeps it apart)",
    linked_help: "RF Devices calls this entity and copies its state: ESPSomfy RTS listens to the remotes and ble_adv remembers what it sends.",
    mirror: "Copy its state (recommended)",
    linked_fill: "Fill the buttons with its actions",
    linked_filled: "Buttons filled with the actions of {e}.",
    linked_none: "No entities of this kind from other integrations.",
    follow: "Follow the original remote",
    follow_help: "The receiver listens all the time: when someone uses the usual remote, RF Devices updates the state without sending anything. Every recognised press fires the rf_devices_remote event (handy in automations, e.g. for an alarm).",
    follow_problem: "This transmitter cannot listen: {msg}",
    follow_somfy: "Real Somfy remotes followed",
    follow_somfy_none: "None yet.",
    follow_somfy_detect: "Detect a Somfy remote",
    follow_somfy_found: "Remote {hex} · button {b} · code {c}",
    follow_somfy_add: "Follow this remote",
    follow_somfy_nothing: "No Somfy frame was recognised in the capture.",
    follow_somfy_title: "Detect a Somfy remote",
    remove_short: "Remove",
  },
};

const TYPE_ICONS = { light: "💡", switch: "🔌", cover: "🪟", fan: "🌀", buttons: "🎛️" };
const COVER_CLASSES = ["shutter", "blind", "curtain", "awning", "shade", "garage", "gate"];
// Somfy button a role gets by default (a Somfy light receiver: up = on, down = off).
const SOMFY_DEFAULT = { open: "up", close: "down", stop: "my", on: "up", off: "down", toggle: "my" };
// Actions offered for a service field, by the domain of the target entity.
const SERVICES = {
  cover: ["cover.open_cover", "cover.close_cover", "cover.stop_cover", "cover.set_cover_position"],
  light: ["light.turn_on", "light.turn_off", "light.toggle"],
  switch: ["switch.turn_on", "switch.turn_off", "switch.toggle"],
  fan: ["fan.turn_on", "fan.turn_off", "fan.set_percentage", "fan.set_preset_mode", "fan.set_direction", "fan.toggle"],
  button: ["button.press"],
  script: ["script.turn_on"],
  scene: ["scene.turn_on"],
  input_boolean: ["input_boolean.turn_on", "input_boolean.turn_off", "input_boolean.toggle"],
  remote: ["remote.send_command"],
};
const hasCode = (c) => !!(c && (c.code || c.kind === "somfy" || c.kind === "action"));

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

/** Command slots for a device; mirrors models.roles() in Python. */
function slotsFor(device) {
  const o = device.options || {};
  let s = [];
  if (device.type === "light" || device.type === "switch") {
    s = (o.mode || (device.type === "light" ? "toggle" : "onoff")) === "toggle" ? [["toggle", true]] : [["on", true], ["off", true]];
  } else if (device.type === "cover") {
    s = [["open", true], ["close", true], ["stop", false]];
  } else if (device.type === "fan") {
    s = [[o.power === "toggle" ? "power" : "off", true]];
    for (let n = 1; n <= (o.speeds || 3); n++) s.push([`speed_${n}`, true]);
    if (o.direction === "toggle") s.push(["direction", true]);
    if (o.direction === "buttons") s.push(["forward", true], ["reverse", true]);
    (o.presets || []).forEach((_, i) => s.push([`preset_${i + 1}`, true]));
    if (o.light === "toggle") s.push(["light_toggle", true]);
    if (o.light === "onoff") s.push(["light_on", true], ["light_off", true]);
  }
  if (device.type === "fan") (o.timers || []).forEach((_, i) => s.push([`timer_${i + 1}`, false]));
  const hasLight = device.type === "light" || (device.type === "fan" && o.light && o.light !== "none");
  if (hasLight && o.light_color) s.push(["light_color", false]);
  if (hasLight && o.light_dim) s.push(["light_up", false], ["light_down", false]);
  const extras = Object.keys(device.commands || {}).filter((r) => r.startsWith("x_")).map((r) => [r, false]);
  return [...s, ...extras].map(([role, required]) => ({ role, required }));
}

class RFDevicesPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._state = { view: "list", devices: [], info: null, draft: null, dialog: null, toast: null };
    this._unsubLearn = null;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._load();
    else this._refreshLive();
  }

  /** Entities whose live state the cards show: meter, relay, wall switch. */
  liveEntities(d) {
    const o = d.options || {};
    const meter = o.state_entity || o.light_state_entity;
    const threshold = o.state_entity ? o.state_threshold : o.light_state_threshold;
    return { meter, threshold: threshold ?? 3, relay: o.power_entity, wall: o.switch_entity };
  }

  liveInfo(d) {
    const { meter, threshold, relay, wall } = this.liveEntities(d);
    const st = this._hass.states;
    const chips = [];
    const onoff = (s) => (s === "on" ? this.t("live_on") : s === "off" ? this.t("live_off") : s ?? "—");
    if (meter && st[meter]) {
      const m = st[meter];
      const unit = m.attributes.unit_of_measurement;
      const lv = this._live?.entity === meter && this._live.watts !== undefined ? this._live.watts : null;
      const num = lv ?? Number(m.state);
      const lit = unit ? num > threshold : m.state === "on";
      chips.push(`<span class="live ${lit ? "on" : ""}" title="${esc(meter)}">⚡ ${this.t("live_meter")}: ${esc(unit ? `${this.fmt(num)} ${unit}` : onoff(m.state))} · ${lit ? this.t("live_light_on") : this.t("live_light_off")}</span>`);
    }
    if (relay && st[relay]) chips.push(`<span class="live ${st[relay].state === "on" ? "on" : "off"}" title="${esc(relay)}">🔌 ${this.t("live_relay")}: ${onoff(st[relay].state)}</span>`);
    if (wall && st[wall]) chips.push(`<span class="live ${st[wall].state === "on" ? "on" : ""}" title="${esc(wall)}">🔘 ${this.t("live_switch")}: ${onoff(st[wall].state)}</span>`);
    return chips.join("");
  }

  _refreshLive(force = false) {
    // Update only the live parts so typing in the editor is never interrupted.
    const root = this.shadowRoot;
    if (this._state.view === "edit" && this._state.draft) {
      for (const id of ["live-body", "live-inline"]) {
        const el = root?.getElementById(id);
        if (!el) continue;
        const active = root.activeElement;
        if (!force && active && el.contains(active) && active.type === "range") continue; // dragging
        const html = this.renderLive();
        if (el.innerHTML !== html) el.innerHTML = html;
      }
    }
    root?.querySelectorAll("[data-live]").forEach((el) => {
      const id = el.dataset.live;
      const d = id === "draft" ? this._state.draft : this._state.devices.find((x) => x.id === id);
      if (!d) return;
      const html = this.liveInfo(d);
      if (el.innerHTML !== html) el.innerHTML = html;
    });
  }

  set narrow(v) {
    this._narrow = v;
  }

  set panel(v) {}

  disconnectedCallback() {
    if (this._state.measure) clearInterval(this._state.measure.timer);
    this._state.measure = null;
    this._stopLearn();
    if (this._liveUnsub) this._liveUnsub().catch(() => {});
    this._liveUnsub = null;
    this._live = null;
  }

  // ---------- helpers ----------
  /** Number as typed: "0,5" and "0.5" both work; clamped to the field's limits. */
  num(el) {
    const raw = String(el.value).trim().replace(",", ".");
    if (raw === "") return null;
    let v = Number(raw);
    if (Number.isNaN(v)) return null;
    const lo = el.dataset.min ?? el.getAttribute("min");
    const hi = el.dataset.max ?? el.getAttribute("max");
    if (lo !== null && lo !== undefined && lo !== "") v = Math.max(Number(lo), v);
    if (hi !== null && hi !== undefined && hi !== "") v = Math.min(Number(hi), v);
    return Math.round(v * 100) / 100;
  }

  /** Show decimals the way the user writes them (comma in Spanish). */
  fmt(v) {
    if (v === null || v === undefined || v === "") return "";
    const text = String(v);
    return (this._hass?.language || "en").startsWith("es") ? text.replace(".", ",") : text;
  }

  t(key, vars = {}) {
    const lang = (this._hass?.language || "en").startsWith("es") ? "es" : "en";
    let s = I18N[lang][key] ?? I18N.en[key] ?? key;
    for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v);
    return s;
  }

  roleLabel(role, device) {
    if (role.startsWith("speed_")) return this.t("r_speed", { n: role.slice(6) });
    if (role.startsWith("timer_")) return this.t("r_timer", { label: device?.options?.timers?.[Number(role.slice(6)) - 1] || role.slice(6) });
    if (role.startsWith("preset_")) return device?.options?.presets?.[Number(role.slice(7)) - 1] || role;
    if (role.startsWith("x_")) return device?.commands?.[role]?.label || role.slice(2);
    return this.t(`r_${role}`);
  }

  ws(msg) {
    return this._hass.callWS(msg);
  }

  toast(text, error = false) {
    this._state.toast = { text, error };
    this.render();
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      this._state.toast = null;
      this.render();
    }, 4000);
  }

  async _load() {
    try {
      const [info, devices] = await Promise.all([this.ws({ type: "rf_devices/info" }), this.ws({ type: "rf_devices/devices" })]);
      Object.assign(this._state, { info, devices });
    } catch (e) {
      this._state.error = e.message || String(e);
    }
    this.render();
  }

  // ---------- actions ----------
  newDevice() {
    this._state.draft = { id: null, name: "", type: "light", transmitter: null, options: {}, commands: {} };
    this.setType("light");
    this._state.view = "edit";
    this._state.tab = "general";
    this.render();
  }

  editDevice(id) {
    const d = this._state.devices.find((x) => x.id === id);
    this._state.draft = JSON.parse(JSON.stringify(d));
    this._state.view = "edit";
    this._state.tab = "general";
    this._state.saveStatus = "saved";
    this.render();
  }

  async deleteDevice(id) {
    const d = this._state.devices.find((x) => x.id === id);
    if (!confirm(this.t("confirm_delete", { name: d.name }))) return;
    await this.ws({ type: "rf_devices/device/delete", device_id: id });
    this._state.devices = this._state.devices.filter((x) => x.id !== id);
    this.render();
  }

  isSaved() {
    const d = this._state.draft;
    return !!(d?.id && this._state.devices.some((x) => x.id === d.id));
  }

  /** Any change in the editor: saved devices save themselves shortly after. */
  dirty() {
    if (!this.isSaved()) return;
    this._state.saveStatus = "dirty";
    this._paintStatus();
    clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => this.persist(), 1200);
  }

  async persist() {
    clearTimeout(this._saveTimer);
    const d = this._state.draft;
    if (!d || !d.name.trim()) return false;
    const commands = Object.fromEntries(Object.entries(d.commands).filter(([, c]) => hasCode(c)));
    this._state.saveStatus = "saving";
    this._paintStatus();
    try {
      const plain = Object.fromEntries(Object.entries(d).filter(([k]) => !k.startsWith("_")));
      const saved = await this.ws({ type: "rf_devices/device/save", device: { ...plain, commands } });
      // The server may change names (take the relay's name) or assign the id.
      d.id = saved.id;
      d.name = saved.name;
      d.rev = saved.rev;
      for (const k of ["light_name", "take_relay_name", "take_name_backup", "take_relay_entity_id",
        "entity_id_backup", "power_entity"]) d.options[k] = saved.options[k];
      for (const k of ["somfy_code", "somfy_note", "follow_problem"]) d[k] = saved[k];
      const i = this._state.devices.findIndex((x) => x.id === saved.id);
      if (i >= 0) this._state.devices[i] = saved;
      else this._state.devices.push(saved);
      this._state.saveStatus = "saved";
      this._reloadedAt = Date.now();
      setTimeout(() => this._refreshDevices(), 2500); // entity ids after the reload
      this._paintStatus();
      return true;
    } catch (e) {
      if (e.code === "stale") {
        // Changed elsewhere (another tab, a script, calibration): take that
        // version instead of overwriting it.
        await this._refreshDevices();
        const fresh = this._state.devices.find((x) => x.id === d.id);
        if (fresh && this._state.draft?.id === d.id) this._state.draft = JSON.parse(JSON.stringify(fresh));
        this._state.saveStatus = "saved";
        this.toast(this.t("stale_reloaded"));
        return false;
      }
      this._state.saveStatus = "error";
      this._paintStatus();
      this.toast(e.message, true);
      return false;
    }
  }

  async _refreshDevices() {
    try {
      this._state.devices = await this.ws({ type: "rf_devices/devices" });
      this._refreshLive(true);
    } catch (e) {
      /* next time */
    }
  }

  _paintStatus() {
    const el = this.shadowRoot?.getElementById("save-status");
    if (!el) return;
    const st = this._state.saveStatus || "saved";
    el.className = `save-status ${st}`;
    el.textContent = this.t("st_" + st);
  }

  async saveDraft() {
    const d = this._state.draft;
    if (!d.name.trim()) {
      this.toast(this.t("name") + "?", true);
      return;
    }
    if (await this.persist()) {
      this.toast(this.t("saved"));
      this.render();
    }
  }

  setType(type) {
    this.dirty();
    const d = this._state.draft;
    d.type = type;
    d.options =
      type === "light" ? { mode: "toggle", switch_entity: null, state_entity: null, state_threshold: 3, power_entity: null, power_on_allowed: false }
      : type === "switch" ? { mode: "onoff", switch_entity: null, state_entity: null, state_threshold: 3, power_entity: null }
      : type === "cover" ? { open_time: 0, close_time: 0, device_class: "shutter", power_entity: null, state_entity: null, state_threshold: 3, switch_entity: null, switch_close_entity: null, wall_type: "momentary" }
      : type === "fan" ? { speeds: 3, power: "off", direction: "none", presets: [], light: "none", light_state_entity: null, light_state_threshold: 3, power_entity: null }
      : {};
    this.render();
  }

  async send(code, transmitter) {
    try {
      await this.ws({ type: "rf_devices/code/send", code, transmitter: transmitter || this._state.draft?.transmitter || null });
      this.toast(this.t("sent"));
    } catch (e) {
      this.toast(e.message, true);
    }
  }

  async cleanRole(role) {
    const cmd = this._state.draft.commands[role];
    const r = await this.ws({ type: "rf_devices/code/clean", code: cmd.code });
    Object.assign(cmd, { code: r.code, analysis: r.analysis, fingerprint: r.fingerprint });
    this.dirty();
    this.render();
  }

  setCommand(role, result, useRaw = false) {
    const d = this._state.draft;
    const prev = d.commands[role] || {};
    d.commands[role] = {
      label: prev.label ?? null,
      hold: prev.hold ?? 0,
      source: null,
      code: useRaw ? result.raw : result.code,
      analysis: useRaw ? result.raw_analysis : result.analysis,
      fingerprint: result.fingerprint,
      frequency: result.frequency ?? prev.frequency ?? null,
      learned: new Date().toISOString(),
    };
    this._state.dialog = null;
    this.dirty();
    this.render();
  }

  addExtra() {
    const input = this.shadowRoot.getElementById("extra-name");
    const label = input.value.trim();
    if (!label) return;
    let base = "x_" + label.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 30);
    if (base === "x_") base = "x_btn";
    let role = base;
    for (let n = 2; this._state.draft.commands[role]; n++) role = `${base}_${n}`;
    // Placeholder until captured: kept only in the draft.
    this._state.draft.commands[role] = { label, code: null };
    this.render();
    this.openLearn(role);
  }

  // ---------- learning ----------
  openLearn(role) {
    const tx = this._state.draft.transmitter || this._state.info.default_transmitter;
    const sweeps = this._state.info.transmitters.find((t) => t.entity_id === tx)?.sweeps ?? true;
    const freq = sweeps ? this._state.info.frequencies?.[tx] : null;
    this._state.dialog = { kind: "learn", role, stage: "idle", useKnown: !!freq, knownFreq: freq, tx };
    this.render();
  }

  async startLearn() {
    const dlg = this._state.dialog;
    this._stopLearn();
    Object.assign(dlg, { stage: "starting", result: null, message: null, started: Date.now() });
    this.render();
    try {
      this._unsubLearn = await this._hass.connection.subscribeMessage(
        (ev) => {
          if (this._state.dialog !== dlg) return;
          dlg.stage = ev.stage;
          if (ev.frequency) {
            dlg.frequency = ev.frequency;
            this._state.info.frequencies = { ...(this._state.info.frequencies || {}), [dlg.tx]: ev.frequency };
          }
          if (ev.stage === "captured") {
            dlg.result = ev;
            if (dlg.somfyDetect) this.decodeSomfy(dlg);
          }
          if (ev.stage === "error") {
            dlg.message = ev.message;
            dlg.reason = ev.reason;
          }
          if (["captured", "timeout", "error"].includes(ev.stage)) this._stopLearn();
          this.render();
        },
        { type: "rf_devices/learn", transmitter: dlg.tx, frequency: dlg.useKnown ? dlg.knownFreq : null }
      );
    } catch (e) {
      Object.assign(dlg, { stage: "error", message: e.message });
      this.render();
    }
  }

  /** While the editor is open, read the device's meter live every second. */
  async _watchMeter() {
    const d = this._state.view === "edit" ? this._state.draft : null;
    const meter = d && (d.options.light_state_entity || d.options.state_entity);
    const wanted = meter && meter.startsWith("sensor.") ? meter : null;
    if ((this._live?.entity || null) === wanted) return;
    if (this._liveUnsub) {
      this._liveUnsub().catch(() => {});
      this._liveUnsub = null;
    }
    this._live = wanted ? { entity: wanted } : null;
    if (!wanted) return;
    try {
      this._liveUnsub = await this._hass.connection.subscribeMessage((ev) => {
        if (this._live?.entity !== wanted) return;
        Object.assign(this._live, ev);
        this._refreshLive(true);
      }, { type: "rf_devices/meter/live", entity_id: wanted });
    } catch (e) {
      this._live = null;
    }
  }

  _stopLearn() {
    if (this._unsubLearn) {
      this._unsubLearn().catch(() => {});
      this._unsubLearn = null;
    }
  }

  closeDialog() {
    this._stopLearn();
    const dlg = this._state.dialog;
    // Drop an extra button that was never captured.
    if (dlg?.role?.startsWith("x_") && this._state.draft?.commands[dlg.role]?.code === null) {
      delete this._state.draft.commands[dlg.role];
    }
    this._state.dialog = null;
    this.render();
  }

  async analyzePasted() {
    const code = this.shadowRoot.getElementById("paste-code").value.trim();
    try {
      this._state.dialog.result = await this.ws({ type: "rf_devices/code/analyze", code });
      this._state.dialog.message = null;
    } catch (e) {
      this._state.dialog.message = e.message;
    }
    this.render();
  }

  async openBroadlink(role) {
    this._state.dialog = { kind: "broadlink", role, codes: null };
    this.render();
    this._state.dialog.codes = await this.ws({ type: "rf_devices/broadlink_codes" });
    this.render();
  }

  openDevices(role) {
    // Saved devices plus the one being edited (it may hold unsaved codes).
    const list = this._state.devices.filter((d) => d.id !== this._state.draft.id).concat([this._state.draft]);
    this._state.dialog = { kind: "devices", role, list };
    this.render();
  }

  showCode(role) {
    const code = this._state.draft.commands[role].code;
    this._state.dialog = { kind: "code", role, code };
    this.render();
    navigator.clipboard?.writeText("b64:" + code).then(() => this.toast(this.t("copied")), () => {});
  }

  async useBroadlink(code) {
    const role = this._state.dialog.role;
    const result = await this.ws({ type: "rf_devices/code/analyze", code });
    this._state.dialog = { kind: "paste", role, result };
    this.render();
  }

  // ---------- export / import ----------
  async exportAll() {
    const data = await this.ws({ type: "rf_devices/export" });
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `rf_devices_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  async downloadDebug() {
    try {
      const data = await this.ws({ type: "rf_devices/debug_report" });
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `rf_devices_debug_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (e) {
      this.toast(e.message, true);
    }
  }

  async importFile(file) {
    try {
      const data = JSON.parse(await file.text());
      const replace = confirm(this.t("import_replace"));
      const r = await this.ws({ type: "rf_devices/import", data, replace });
      this.toast(this.t("import_done", r));
      await this._load();
      setTimeout(() => this._load(), 2500);
    } catch (e) {
      this.toast(e.message, true);
    }
  }

  // ---------- other kinds of buttons (Somfy, Home Assistant actions) ----------
  /** A command as the server stores it (the editor adds analysis and the like). */
  cleanCmd(c) {
    const keep = ["kind", "code", "frequency", "learned", "label", "hold", "source", "button", "service", "entity_id", "data"];
    return Object.fromEntries(Object.entries(c).filter(([k, v]) => keep.includes(k) && v !== undefined));
  }

  async testRole(role) {
    const c = this._state.draft.commands[role];
    if (!c.kind || c.kind === "rf") return this.send(c.code);
    return this.sendCommand(c);
  }

  async sendCommand(command) {
    const d = this._state.draft;
    try {
      const r = await this.ws({
        type: "rf_devices/command/send",
        device: { id: d.id, name: d.name, transmitter: d.transmitter || null, somfy: d.somfy || null },
        command: this.cleanCmd(command),
      });
      if (r && r.somfy_code !== undefined) d.somfy_code = r.somfy_code;
      this.toast(this.t("sent"));
      return true;
    } catch (e) {
      this.toast(e.message, true);
      return false;
    }
  }

  controlOf(d) {
    return d.somfy ? "somfy" : d.linked_entity || d._linking ? "linked" : "rf";
  }

  async setControl(value) {
    const d = this._state.draft;
    if (value !== "somfy" && d.somfy) {
      d.somfy = null;
      for (const [role, c] of Object.entries(d.commands)) if (c.kind === "somfy") delete d.commands[role];
      d.follow_somfy = [];
    }
    if (value !== "linked") {
      d.linked_entity = null;
      d.linked_light_entity = null;
      d.mirror = false;
      d._linking = false;
    }
    if (value === "somfy" && !d.somfy) {
      const { address } = await this.ws({ type: "rf_devices/somfy/new_address" });
      d.somfy = { address, invert: false, repeats: 4 };
      d.somfy_code = 0;
      this.fillSomfy(false);
    }
    if (value === "linked") {
      d._linking = true;
      d.mirror = true;
    }
    this.dirty();
    this.render();
  }

  /** Somfy buttons for the roles that have nothing yet (or all of them). */
  fillSomfy(all = true) {
    const d = this._state.draft;
    if (d.type === "light" || d.type === "switch") d.options.mode = "onoff";
    for (const { role } of slotsFor(d)) {
      const button = SOMFY_DEFAULT[role];
      if (!button || (!all && hasCode(d.commands[role]))) continue;
      d.commands[role] = { kind: "somfy", button, label: d.commands[role]?.label ?? null, hold: 0 };
    }
    if (d.type === "buttons" && !Object.keys(d.commands).length) {
      for (const b of ["up", "my", "down"]) d.commands[`x_${b}`] = { kind: "somfy", button: b, label: this.t("b_" + b), hold: 0 };
    }
  }

  async newSomfyAddress() {
    const d = this._state.draft;
    if (!confirm(this.t("somfy_new_confirm"))) return;
    const { address } = await this.ws({ type: "rf_devices/somfy/new_address" });
    d.somfy = { ...d.somfy, address };
    d.somfy_code = 0;
    this.dirty();
    this.render();
  }

  async pairSomfy() {
    if (await this.sendCommand({ kind: "somfy", button: "prog" })) this.toast(this.t("somfy_pair_sent"));
    this.render();
  }

  async loadLinkable(kind) {
    this._state.linkable = this._state.linkable || {};
    if (this._state.linkable[kind] || this._linkLoading?.[kind]) return;
    this._linkLoading = { ...(this._linkLoading || {}), [kind]: true };
    try {
      this._state.linkable[kind] = await this.ws({ type: "rf_devices/linkable", kind });
    } catch (e) {
      this._state.linkable[kind] = [];
    }
    this._linkLoading[kind] = false;
    this.render();
  }

  /** Buttons that call the linked entity's actions, and options that match it. */
  fillLinked() {
    const d = this._state.draft;
    const eid = d.linked_entity;
    if (!eid) return;
    const dom = eid.split(".")[0];
    const act = (service, data = {}, entity = eid) => ({ kind: "action", service, entity_id: entity, data, label: null, hold: 0 });
    const st = this._hass.states[eid];
    const a = st?.attributes || {};
    const cmds = {};
    if (d.type === "cover") {
      Object.assign(cmds, { open: act("cover.open_cover"), close: act("cover.close_cover"), stop: act("cover.stop_cover") });
    } else if (d.type === "light" || d.type === "switch") {
      d.options.mode = "onoff";
      Object.assign(cmds, { on: act(`${dom}.turn_on`), off: act(`${dom}.turn_off`) });
    } else if (d.type === "fan") {
      const n = Math.max(1, Math.min(this._state.info.max_speeds, Math.round(100 / (a.percentage_step || 100 / 3))));
      Object.assign(d.options, { speeds: n, power: "off", turn_on_speed: d.options.turn_on_speed ?? 1 });
      cmds.off = act("fan.turn_off");
      for (let i = 1; i <= n; i++) cmds[`speed_${i}`] = act("fan.set_percentage", { percentage: Math.round((i * 100) / n) });
      const presets = (a.preset_modes || []).slice(0, 6);
      d.options.presets = presets;
      presets.forEach((p, i) => (cmds[`preset_${i + 1}`] = act("fan.set_preset_mode", { preset_mode: p })));
      if ((a.supported_features || 0) & 4) {
        d.options.direction = "buttons";
        cmds.forward = act("fan.set_direction", { direction: "forward" });
        cmds.reverse = act("fan.set_direction", { direction: "reverse" });
      }
      if (d.linked_light_entity) {
        d.options.light = "onoff";
        if (!d.options.light_name) d.options.light_name = this.defaultLightName();
        cmds.light_on = act("light.turn_on", {}, d.linked_light_entity);
        cmds.light_off = act("light.turn_off", {}, d.linked_light_entity);
      }
    }
    for (const [role, c] of Object.entries(cmds)) c.label = d.commands[role]?.label ?? null;
    for (const role of Object.keys(d.commands)) if (!role.startsWith("x_")) delete d.commands[role];
    Object.assign(d.commands, cmds);
    this.toast(this.t("linked_filled", { e: eid }));
  }

  defaultService(role) {
    const d = this._state.draft;
    const eid = role.startsWith("light_") && d.linked_light_entity ? d.linked_light_entity : d.linked_entity;
    const dom = eid ? eid.split(".")[0] : d.type === "buttons" ? "button" : d.type;
    const by = {
      open: "cover.open_cover", close: "cover.close_cover", stop: "cover.stop_cover",
      on: `${dom}.turn_on`, off: `${dom}.turn_off`, toggle: `${dom}.toggle`, power: "fan.toggle",
      light_on: "light.turn_on", light_off: "light.turn_off", light_toggle: "light.toggle",
    };
    if (role.startsWith("speed_")) return "fan.set_percentage";
    if (role.startsWith("preset_")) return "fan.set_preset_mode";
    return by[role] || (dom === "button" ? "button.press" : "");
  }

  openAction(role) {
    const d = this._state.draft;
    const c = d.commands[role];
    const cur = c?.kind === "action" ? c : null;
    const entity = cur ? cur.entity_id
      : role.startsWith("light_") && d.linked_light_entity ? d.linked_light_entity : d.linked_entity;
    this._state.dialog = {
      kind: "action", role,
      service: cur?.service || this.defaultService(role),
      entity_id: entity || "",
      data: cur && Object.keys(cur.data || {}).length ? JSON.stringify(cur.data) : "",
      message: null,
    };
    this.render();
  }

  /** The action typed in the dialog, or null (and a message) if it is not valid. */
  readAction() {
    const dlg = this._state.dialog;
    const root = this.shadowRoot;
    dlg.service = root.getElementById("action-service").value.trim();
    dlg.entity_id = root.getElementById("action-entity").value || "";
    dlg.data = root.getElementById("action-data").value.trim();
    if (!/^[a-z0-9_]+\.[a-z0-9_]+$/.test(dlg.service)) {
      dlg.message = this.t("action_bad_service");
      this.render();
      return null;
    }
    let data = {};
    if (dlg.data) {
      try {
        data = JSON.parse(dlg.data);
        if (typeof data !== "object" || Array.isArray(data) || data === null) throw new Error();
      } catch (e) {
        dlg.message = this.t("action_bad_json");
        this.render();
        return null;
      }
    }
    const prev = this._state.draft.commands[dlg.role];
    return { kind: "action", service: dlg.service, entity_id: dlg.entity_id || null, data, label: prev?.label ?? null, hold: 0 };
  }

  saveAction() {
    const cmd = this.readAction();
    if (!cmd) return;
    this._state.draft.commands[this._state.dialog.role] = cmd;
    this._state.dialog = null;
    this.dirty();
    this.render();
  }

  setSomfyButton(role, button) {
    const d = this._state.draft;
    const prev = d.commands[role];
    d.commands[role] = { kind: "somfy", button, label: prev?.label ?? null, hold: prev?.kind === "somfy" ? prev.hold || 0 : 0 };
    this.dirty();
    this.render();
  }

  openSomfyDetect() {
    const tx = this._state.draft.transmitter || this._state.info.default_transmitter;
    this._state.dialog = { kind: "learn", role: null, somfyDetect: true, stage: "idle", useKnown: false, knownFreq: null, tx };
    this.render();
  }

  async decodeSomfy(dlg) {
    try {
      dlg.somfy = await this.ws({ type: "rf_devices/somfy/decode", code: dlg.result.raw });
    } catch (e) {
      dlg.somfy = [];
    }
    this.render();
  }

  addFollowSomfy(address) {
    const d = this._state.draft;
    d.follow_somfy = [...new Set([...(d.follow_somfy || []), Number(address)])];
    d.follow = true;
    this._state.dialog = null;
    this.dirty();
    this.render();
  }

  txInfo(d) {
    const id = d.transmitter || this._state.info.default_transmitter;
    return this._state.info.transmitters.find((t) => t.entity_id === id);
  }

  renderControl(d) {
    const ctl = this.controlOf(d);
    const choices = [["rf", this.t("control_rf")]];
    if (["cover", "light", "switch", "buttons"].includes(d.type)) choices.push(["somfy", this.t("control_somfy")]);
    if (d.type !== "buttons") choices.push(["linked", this.t("control_linked")]);
    const body = ctl === "somfy" ? this.renderSomfy(d) : ctl === "linked" ? this.renderLinked(d) : "";
    return `<div class="form ctl">
      <h3 class="full">${this.t("control_title")}</h3>
      <label class="full"><select data-action="control">
        ${choices.map(([v, l]) => `<option value="${v}" ${ctl === v ? "selected" : ""}>${esc(l)}</option>`).join("")}
      </select><small>${this.t("control_help")}</small></label>
      ${body}
      ${this.renderFollow(d)}
    </div>`;
  }

  renderSomfy(d) {
    const s = d.somfy;
    const hex = Number(s.address).toString(16).toUpperCase().padStart(6, "0");
    const note = this.txInfo(d)?.somfy_note;
    return `
      <label>${this.t("somfy_address")}<input readonly value="${hex}"></label>
      <label>${this.t("somfy_repeats")}<input type="number" min="0" max="20" data-somfy="repeats" value="${s.repeats ?? 4}"></label>
      <label class="check full"><input type="checkbox" data-somfy="invert" ${s.invert ? "checked" : ""}> ${this.t("somfy_invert")}</label>
      ${d.somfy_code !== undefined && d.somfy_code !== null ? `<small class="full">${this.t("somfy_code", { n: d.somfy_code })}</small>` : ""}
      ${note ? `<p class="warn-text full">${esc(this.t("somfy_note", { msg: note }))}</p>` : ""}
      <small class="full">${this.t("somfy_pair_help")}</small>
      <div class="actions full">
        <button class="primary" data-action="somfy-pair">${this.t("somfy_pair")}</button>
        <button data-action="somfy-fill">${this.t("somfy_fill")}</button>
        <span class="spacer"></span>
        <button data-action="somfy-new">${this.t("somfy_new")}</button>
      </div>`;
  }

  renderLinked(d) {
    const list = this._state.linkable?.[d.type];
    if (!list) queueMicrotask(() => this.loadLinkable(d.type));
    const lights = d.type === "fan" ? this._state.linkable?.fan_light : null;
    if (d.type === "fan" && !lights) queueMicrotask(() => this.loadLinkable("fan_light"));
    const options = (items, selected) => {
      const known = (items || []).some((e) => e.entity_id === selected);
      return `<option value="">${this.t("none")}</option>
        ${selected && !known ? `<option value="${esc(selected)}" selected>${esc(selected)}</option>` : ""}
        ${(items || []).map((e) => `<option value="${esc(e.entity_id)}" ${selected === e.entity_id ? "selected" : ""}>${esc(e.name)} (${esc(e.entity_id)}${e.platform ? ` · ${esc(e.platform)}` : ""})</option>`).join("")}`;
    };
    return `
      <label class="full">${this.t("linked_entity")}<select data-action="linked">${options(list, d.linked_entity)}</select>
        <small>${list && !list.length ? this.t("linked_none") : this.t("linked_help")}</small></label>
      ${d.type === "fan" ? `<label class="full">${this.t("linked_light")}<select data-action="linked-light">${options(lights, d.linked_light_entity)}</select></label>` : ""}
      <label class="check full"><input type="checkbox" data-action="mirror" ${d.mirror ? "checked" : ""}> ${this.t("mirror")}</label>
      <div class="actions full"><button class="primary" data-action="linked-fill" ${d.linked_entity ? "" : "disabled"}>${this.t("linked_fill")}</button></div>`;
  }

  renderFollow(d) {
    if (d.mirror && d.linked_entity) return ""; // the linked entity already knows the state
    const tx = this.txInfo(d);
    const problem = tx && !tx.can_listen ? tx.listen_problem : null;
    let somfyList = "";
    if (d.somfy && d.follow) {
      const rows = (d.follow_somfy || []).map((a) => {
        const hex = Number(a).toString(16).toUpperCase().padStart(6, "0");
        return `<div class="bl-row"><span class="mono">${hex}</span><button data-action="unfollow-somfy" data-address="${a}">${this.t("remove_short")}</button></div>`;
      }).join("");
      somfyList = `<div class="full"><b>${this.t("follow_somfy")}</b>${rows || `<p class="sub">${this.t("follow_somfy_none")}</p>`}
        <div class="actions"><button data-action="somfy-detect" ${problem ? "disabled" : ""}>${this.t("follow_somfy_detect")}</button></div></div>`;
    }
    return `<label class="check full"><input type="checkbox" data-action="follow" ${d.follow ? "checked" : ""}> ${this.t("follow")}</label>
      <small class="full">${this.t("follow_help")}</small>
      ${d.follow && problem ? `<p class="warn-text full">${esc(this.t("follow_problem", { msg: problem }))}</p>` : ""}
      ${somfyList}`;
  }

  // ---------- rendering ----------
  wave(sampleUs, frameMap) {
    if (!sampleUs?.length) return "";
    const total = sampleUs.reduce((a, b) => a + b, 0);
    const W = 240, H = 26;
    let x = 0, d = `M0 ${H - 3}`;
    sampleUs.forEach((us, i) => {
      const y = i % 2 === 0 ? 3 : H - 3;
      const nx = x + (us / total) * W;
      d += ` L${x.toFixed(1)} ${y} L${nx.toFixed(1)} ${y}`;
      x = nx;
    });
    const blocks = (frameMap || [])
      .map((f) => `<span class="blk ${f.ok ? "ok" : "bad"}" title="${f.pulses}"></span>`)
      .join("");
    return `<div class="wave"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><path d="${d}"/></svg><div class="blocks">${blocks}</div></div>`;
  }

  times(repeat) {
    return repeat === 0 ? this.t("once") : this.t("times", { n: repeat + 1 });
  }

  summary(a) {
    return this.t("summary", { frames: a.frames, bad: a.bad_frames, times: this.times(a.repeat), ms: a.sent_ms });
  }

  renderList() {
    const { devices } = this._state;
    const cards = devices
      .map((d) => {
        const chipsOf = (slots) => slots
          .map((s) => {
            const c = d.commands[s.role];
            const cls = !c ? (s.required ? "missing" : "opt") : c.analysis?.needs_cleaning ? "warn" : "ok";
            return `<span class="chip ${cls}">${esc(this.roleLabel(s.role, d))}</span>`;
          })
          .join("");
        const slots = slotsFor(d);
        const split = d.type === "fan" && this.hasLight(d);
        const chips = split
          ? `<div class="chips"><span class="chip-group">🌀</span>${chipsOf(slots.filter((x) => !x.role.startsWith("light_")))}</div>
             <div class="chips"><span class="chip-group">💡</span>${chipsOf(slots.filter((x) => x.role.startsWith("light_")))}</div>`
          : `<div class="chips">${chipsOf(slots)}</div>`;
        const lightEnts = new Set(d.light_entities || []);
        const entLine = (list) => list.map(esc).join(", ");
        const ents = !d.entities?.length ? ""
          : split && lightEnts.size
            ? `<div class="sub">🌀 ${entLine(d.entities.filter((e) => !lightEnts.has(e)))}</div><div class="sub">💡 ${entLine(d.entities.filter((e) => lightEnts.has(e)))}</div>`
            : `<div class="sub">${this.t("entities")}: ${entLine(d.entities)}</div>`;
        return `<div class="card">
          <div class="card-head"><span class="icon">${TYPE_ICONS[d.type] || "📡"}</span>
            <div><div class="name">${esc(this.remoteTitle(d))}</div><div class="sub">${esc(this.remoteKind(d))}</div></div></div>
          ${chips}
          <div class="lives" data-live="${d.id}">${this.liveInfo(d)}</div>
          ${ents}
          <div class="actions">
            <button data-action="edit" data-id="${d.id}">${this.t("edit")}</button>
            <button class="danger" data-action="delete" data-id="${d.id}">${this.t("delete")}</button>
          </div></div>`;
      })
      .join("");
    return `
      <div class="toolbar">
        <button class="primary" data-action="new">＋ ${this.t("new_device")}</button>
        <button data-action="export">${this.t("export")}</button>
        <button data-action="import">${this.t("import")}</button>
        <button data-action="debug-report" title="${esc(this.t("debug_report_help"))}">${this.t("debug_report")}</button>
        <input type="file" id="import-file" accept="application/json,.json" hidden>
      </div>
      ${devices.length ? `<div class="grid">${cards}</div>` : `<div class="empty">${this.t("empty")}</div>`}`;
  }

  /** Entities RF Devices itself creates: never a relay, wall switch or meter of a device. */
  ownEntities() {
    return new Set(this._state.devices.flatMap((d) => d.entities || []));
  }

  entityOptions(filter, selected) {
    const st = this._hass.states;
    const own = this.ownEntities();
    return Object.keys(st)
      .filter((e) => (!own.has(e) || e === selected) && filter(e, st[e]))
      .sort()
      .map((e) => `<option value="${e}" ${selected === e ? "selected" : ""}>${esc(st[e].attributes.friendly_name || e)} (${e})</option>`)
      .join("");
  }

  entitySelect(opt, label, filter, help = "", extra = []) {
    const o = this._state.draft.options;
    const missing = extra.filter((e) => e && !this._hass.states[e]);
    return `<label>${label}
      <select data-opt="${opt}" data-null="1" data-rerender="1">
        <option value="">${this.t("none")}</option>
        ${missing.map((e) => `<option value="${e}" ${o[opt] === e ? "selected" : ""}>${e}</option>`).join("")}
        ${this.entityOptions(filter, o[opt])}
      </select>${help ? `<small>${help}</small>` : ""}</label>`;
  }

  feedbackFields(entityKey, thresholdKey, label) {
    const o = this._state.draft.options;
    const isFeedback = (e, st) =>
      /^(binary_sensor|input_boolean|switch|light)\./.test(e) || (/^sensor\./.test(e) && st.attributes.unit_of_measurement === "W");
    const chosen = o[entityKey];
    const numeric = chosen && chosen.startsWith("sensor.");
    return this.entitySelect(entityKey, label, isFeedback, this.t("feedback_help")) +
      (numeric ? `<label>${this.t("threshold")}<input class="dec" type="text" inputmode="decimal" data-min="0" data-opt="${thresholdKey}" value="${this.fmt(o[thresholdKey] ?? 3)}"></label>` : "");
  }

  calibrationTable(c, editable = false) {
    const cell = (path, value) =>
      editable
        ? `<input class="dec calcell" type="text" inputmode="decimal" data-cal="${path}" value="${this.fmt(value)}"> W`
        : `${value} W`;
    const modes = c.light_modes || [c.light];
    const names = this.colorNames();
    const lamp = modes[0] - c.idle;
    const live = !!c.direct;
    const band = (w) => Math.max(c.band_w ?? (live ? 0.3 : 1), Math.abs(w) * (c.band_pct ?? (live ? 0.05 : 0.1)));
    const downs = c.speeds_down || [];
    const rows = c.speeds.map((p, i) => {
      const up = p[0];
      const down = downs[i] ?? up;
      const lo = Math.min(up, down), hi = Math.max(up, down);
      const range = `${this.fmt((lo - band(lo)).toFixed(1))}–${this.fmt((hi + band(hi)).toFixed(1))} W`;
      return `<tr><td>${this.t("cal_speed", { n: i + 1 })}</td><td>${cell(`speeds.${i}`, up)}</td>
        <td>${cell(`speeds_down.${i}`, down)}</td><td class="sub">${range}</td><td>${this.fmt((up + lamp).toFixed(1))} W</td></tr>`;
    }).join("");
    const modeRows = modes.map((w, i) =>
      `<tr><td>${this.t("cal_light")} · ${esc(names[i] || String(i + 1))}</td><td></td><td></td><td></td><td>${cell(`light_modes.${i}`, w)}</td></tr>`).join("");
    const close = [];
    const margin = c.direct ? 0.5 : 2;
    c.speeds.forEach((p, i) => { if (i && Math.abs(p[0] - c.speeds[i - 1][0]) < margin) close.push(`${i}–${i + 1}`); });
    return `<table class="cal"><tr><th></th><th>${this.t("cal_up")}</th><th>${this.t("cal_down")}</th><th>${this.t("cal_range")}</th><th>${this.t("cal_light_on")}</th></tr>
      <tr><td>${this.t("cal_idle")}</td><td>${cell("idle", c.idle)}</td><td></td><td></td><td></td></tr>${modeRows}${rows}</table>
      ${modes.length > 1 ? `<div class="full"><b>${this.t("cal_steps")}</b><div class="tl">${modes.map((w, i) => {
          const next = modes[(i + 1) % modes.length];
          const step = Math.round((next - w) * 100) / 100;
          return `<span class="tl-step">${esc(names[i] || i + 1)} → ${esc(names[(i + 1) % modes.length] || ((i + 1) % modes.length) + 1)}: <b>${step > 0 ? "+" : ""}${this.fmt(step)} W</b>${Math.abs(step) < 0.5 ? " ⚠" : ""}</span>`;
        }).join("")}</div><small>${this.t("cal_steps_help")}</small></div>` : ""}
      ${editable ? `<div class="full"><b>${this.t("cal_band")}</b>: ±
          <input class="dec calcell" type="text" inputmode="decimal" data-cal="band_w" value="${this.fmt(c.band_w ?? (c.direct ? 0.3 : 1))}"> W
          / ± <input class="dec calcell" type="text" inputmode="decimal" data-cal="band_pct" value="${this.fmt(Math.round((c.band_pct ?? (c.direct ? 0.05 : 0.1)) * 100))}"> %
          <br><small>${this.t("cal_band_help")}</small></div>
          <small>${this.t("cal_edit_help")}</small>` : ""}
      ${close.length ? `<small class="warn-text">${this.t("cal_warn_close", { list: close.join(", ") })}</small>` : ""}`;
  }

  /** Idle and lamp draw (per colour mode) of a quick lamp calibration. */
  lampSummary(lc) {
    const names = this.colorNames();
    const modes = lc.light_modes || [lc.light];
    const rows = modes.map((w, i) => `<tr><td>💡 ${esc(modes.length > 1 ? names[i] || String(i + 1) : this.t("cal_light"))}</td><td>${this.fmt(w)} W</td><td>+${this.fmt(w - lc.idle)} W</td></tr>`).join("");
    return `<table class="cal"><tr><td>${this.t("cal_idle")}</td><td>${this.fmt(lc.idle)} W</td><td></td></tr>${rows}</table>`;
  }

  calibrationBlock() {
    const o = this._state.draft.options;
    const c = o.calibration;
    const lc = o.light_calibration;
    return `<div class="full calblock">
      ${c ? `<b>${this.t("cal_table", { date: (c.measured || "").slice(0, 10) })}</b>${this.calibrationTable(c, true)}
      <label class="check full"><input type="checkbox" data-opt="live_calibration" ${(o.live_calibration ?? true) ? "checked" : ""}> ${this.t("cal_live")}</label>
      ${c.learned && Object.keys(c.learned).length ? `<small>${this.t("cal_learned", { list: Object.entries(c.learned).map(([k, v]) => `${k.replace("_up", " ↑").replace("_down", " ↓")} (${v.slice(5, 16).replace("T", " ")})`).join(", ") })}</small>` : ""}` : ""}
      ${!c && lc ? `<b>${this.t("cal_light_table", { date: (lc.measured || "").slice(0, 10) })}</b>${this.lampSummary(lc)}` : ""}
      <div class="actions">
        <button data-action="calibrate-light">💡 ${this.t("calibrate_light")}</button>
        <button data-action="calibrate">⚖ ${this.t("calibrate")}</button>
        ${c ? `<button data-action="cal-remove">${this.t("cal_remove")}</button>` : ""}
        ${!c && lc ? `<button data-action="cal-light-remove">${this.t("cal_remove")}</button>` : ""}
      </div><small>${this.t("calibrate_light_help")}</small></div>`;
  }

  openCalibration(lightOnly = false) {
    const d = this._state.draft;
    if (!d.id || !this._state.devices.some((x) => x.id === d.id)) return this.toast(this.t("calibrate_save_first"), true);
    if (!d.options.light_state_entity) return this.toast(this.t("calibrate_need_meter"), true);
    this._state.dialog = { kind: "calibrate", lightOnly, stage: "idle", lines: [], result: null };
    this.render();
  }

  async startCalibration() {
    const dlg = this._state.dialog;
    Object.assign(dlg, { stage: "running", lines: [], result: null, message: null });
    this.render();
    try {
      this._unsubLearn = await this._hass.connection.subscribeMessage((ev) => {
        if (this._state.dialog !== dlg) return;
        if (ev.stage === "meter") dlg.lines.push({ text: ev.direct ? this.t("cal_direct") : this.t("cal_pushed") });
        if (ev.stage === "speed") dlg.lines.push({ wait: this.t("cal_speed_wait", { n: ev.speed }) });
        if (ev.stage === "measured") {
          let label = ev.what === "idle" ? this.t("cal_idle") : ev.what === "light" ? `${this.t("cal_light")}${ev.mode ? ` (${this.t("cal_mode", { n: ev.mode })})` : ""}`
            : `${this.t("cal_speed", { n: ev.speed })} ${ev.direction === "down" ? this.t("cal_down") : this.t("cal_up")}`;
          if (ev.seconds !== undefined) label += ` (${ev.settled ? this.t("cal_took", { s: ev.seconds }) : this.t("cal_unsettled")})`;
          dlg.lines = dlg.lines.filter((l) => !l.wait);
          dlg.lines.push({ text: `${label}: ${ev.watts} W` });
        }
        if (ev.stage === "done") { dlg.stage = "done"; dlg.result = ev.calibration; this._stopLearn(); }
        if (ev.stage === "error") { dlg.stage = "error"; dlg.message = ev.message; this._stopLearn(); }
        this.render();
      }, { type: "rf_devices/calibrate", device_id: this._state.draft.id, light_only: !!dlg.lightOnly });
    } catch (e) {
      Object.assign(dlg, { stage: "error", message: e.message });
      this.render();
    }
  }

  defaultLightName() {
    const n = (this._state.draft.name || "").trim();
    return this._hass.language?.startsWith("es") ? `Luz ${n.toLowerCase()}` : `${n} light`;
  }

  colorNames() {
    const o = this._state.draft.options;
    const n = o.light_colors ?? 3;
    return Array.from({ length: n }, (_, i) => (o.light_color_names || [])[i] || String(i + 1));
  }

  lightExtras() {
    const o = this._state.draft.options;
    const box = (opt) => `<label class="check full"><input type="checkbox" data-opt="${opt}" data-rerender="1" ${o[opt] ? "checked" : ""}> ${this.t(opt)}</label>`;
    const n = o.light_colors ?? 3;
    const names = this.colorNames();
    return box("light_color") +
      (o.light_color
        ? `<label>${this.t("light_colors")}<input type="number" min="1" max="6" data-opt="light_colors" data-rerender="1" value="${n}"></label>
           <label>${this.t("color_names")}<input data-opt="light_color_names" data-list="1" data-rerender="1" value="${esc((o.light_color_names || []).join(", "))}" placeholder="Frío, Neutro, Cálido"><small>${this.t("color_names_help")}</small></label>
           <label>${this.t("color_power_up")}<select data-opt="light_color_power_up" data-rerender="1">
             ${[["memory", "cpu_memory"], ["fixed", "cpu_fixed"], ["quick_cycle", "cpu_quick"]].map(([v, k]) =>
               `<option value="${v}" ${(o.light_color_power_up || "memory") === v ? "selected" : ""}>${this.t(k)}</option>`).join("")}</select></label>
           ${(o.light_color_power_up || "memory") === "fixed"
             ? `<label>${this.t("color_start_fixed")}<select data-opt="light_color_start" data-num="1">
                 ${names.map((nm, i) => `<option value="${i + 1}" ${(o.light_color_start ?? 1) === i + 1 ? "selected" : ""}>${esc(nm)}</option>`).join("")}</select></label>`
             : ""}
           <label>${this.t("color_kelvin")}<input data-opt="light_color_kelvin" data-list="1" data-nums="1" value="${esc((o.light_color_kelvin || []).join(", "))}" placeholder="6000, 4000, 2700"><small>${this.t("color_kelvin_help")}</small></label>`
        : "") +
      box("light_dim") +
      (o.light_dim ? `<label>${this.t("dim_time")}<input class="dec" type="text" inputmode="decimal" data-min="0.5" data-max="30" data-opt="light_dim_time" value="${this.fmt(o.light_dim_time ?? 5)}"></label>` : "");
  }

  relayOn(d) {
    return ["coupled", "detached"].includes(this.relayMode(d));
  }

  relayMode(d) {
    if (d.type === "cover") return "none"; // a cover has its own, simpler relay options
    return d.options.relay_mode || (d.options.power_entity ? "coupled" : "none");
  }

  diagram(d) {
    const mode = this.relayMode(d);
    const b = mode === "detached" || mode === "wall_only";
    const wallOnly = mode === "wall_only";
    const load = d.type === "fan" ? this.t("d_fan") : this.t("d_light");
    const box = (x, y, w, label, sub = "") => `<g><rect x="${x}" y="${y}" width="${w}" height="44" rx="8" class="dg-box"/>
      <text x="${x + w / 2}" y="${y + (sub ? 19 : 27)}" class="dg-t">${esc(label)}</text>${sub ? `<text x="${x + w / 2}" y="${y + 35}" class="dg-s">${esc(sub)}</text>` : ""}</g>`;
    return `<svg class="diagram" viewBox="0 0 560 170" role="img" aria-label="${esc(this.t("relay_title"))}">
      <defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="dg-ar"/></marker></defs>
      ${box(10, 20, 110, this.t("d_wall"))}
      ${wallOnly ? "" : box(190, 20, 130, this.t("d_relay"), this.t("d_meter"))}
      ${box(400, 20, 150, load)}
      ${box(190, 110, 130, "Home Assistant", "RF Devices")}
      ${box(400, 110, 150, this.t("d_rf"))}
      ${wallOnly ? "" : `<line x1="320" y1="42" x2="398" y2="42" class="dg-power" marker-end="url(#ar)"/>`}
      ${b
        ? `<path d="M65 64 V132 H188" class="dg-data" marker-end="url(#ar)"/>
           ${wallOnly ? "" : `<line x1="120" y1="42" x2="188" y2="42" class="dg-cut"/><text x="154" y="36" class="dg-x">✕</text>`}`
        : `<line x1="120" y1="42" x2="188" y2="42" class="dg-power" marker-end="url(#ar)"/>`}
      ${wallOnly ? "" : `<line x1="255" y1="66" x2="255" y2="108" class="dg-data" marker-start="url(#ar)" marker-end="url(#ar)"/>`}
      <line x1="320" y1="132" x2="398" y2="132" class="dg-data" marker-end="url(#ar)"/>
      <line x1="475" y1="108" x2="475" y2="66" class="dg-rf" marker-end="url(#ar)"/>
    </svg>`;
  }

  /** Covers: what is wired, chosen by the user or read from the saved options. */
  coverWiring(d) {
    const w = this._state.coverWiring;
    if (w && w.id === d.id) return w.value;
    const o = d.options;
    const wall = o.switch_entity || o.switch_close_entity;
    return o.power_entity ? (wall ? "relay_wall" : "relay") : wall ? "wall" : "none";
  }

  /** Covers: a relay feeding the motor and wall buttons, each on its own; a meter. */
  renderCoverRelay(d) {
    const o = d.options;
    const wiring = this.coverWiring(d);
    const relay = wiring.startsWith("relay");
    const wall = wiring.endsWith("wall");
    const isMeter = (e, st) =>
      /^(binary_sensor|input_boolean)\./.test(e) || (/^sensor\./.test(e) && st.attributes.unit_of_measurement === "W");
    const isInput = (e) => /^(binary_sensor|input_boolean|switch)\./.test(e);
    const numeric = o.state_entity && o.state_entity.startsWith("sensor.");
    const opt = (v) => `<option value="${v}" ${wiring === v ? "selected" : ""}>${this.t("cover_wiring_" + v)}</option>`;
    return `<div class="form">
      <label class="full">${this.t("cover_wiring_q")}
        <select data-cover-wiring="1">${["none", "wall", "relay", "relay_wall"].map(opt).join("")}</select>
        <small>${this.t("cover_relay_intro")}</small></label>
      ${relay
        ? `${this.entitySelect("power_entity", this.t("relay_entity"), (e) => /^(switch|light)\./.test(e), this.t("cover_relay_help"))}
           ${o.power_entity
             ? `<label class="check full"><input type="checkbox" data-opt="power_on_allowed" data-rerender="1" ${(o.power_on_allowed ?? true) ? "checked" : ""}> ${this.t("cover_power_on")}</label>
                ${(o.power_on_allowed ?? true)
                  ? `<label>${this.t("power_up_delay")}<input class="dec" type="text" inputmode="decimal" data-min="0" data-max="15" data-opt="power_up_delay" value="${this.fmt(o.power_up_delay ?? 1)}"><small>${this.t("cover_power_up_delay_help")}</small></label>`
                  : ""}`
             : ""}`
        : ""}
      ${wall
        ? `<label>${this.t("cover_wall_type")}<select data-opt="wall_type" data-rerender="1">
             <option value="momentary" ${(o.wall_type || "momentary") === "momentary" ? "selected" : ""}>${this.t("cover_wall_momentary")}</option>
             <option value="maintained" ${o.wall_type === "maintained" ? "selected" : ""}>${this.t("cover_wall_maintained")}</option></select></label>
           ${this.entitySelect("switch_entity", this.t(o.switch_close_entity ? "cover_wall_up" : "cover_wall_one"), isInput)}
           ${this.entitySelect("switch_close_entity", this.t("cover_wall_down"), isInput)}
           <small class="full">${this.t(o.switch_close_entity
             ? (o.wall_type === "maintained" ? "cover_wall_two_maintained_help" : "cover_wall_two_help")
             : (o.wall_type === "maintained" ? "cover_wall_one_maintained_help" : "cover_wall_one_help"))}</small>`
        : ""}
      <h3 class="full">${this.t("meter_entity")}</h3>
      ${this.entitySelect("state_entity", this.t("meter_entity"), isMeter, this.t("cover_meter_help"))}
      ${numeric ? `<label>${this.t("cover_threshold")}<input class="dec" type="text" inputmode="decimal" data-min="0" data-opt="state_threshold" value="${this.fmt(o.state_threshold ?? 3)}"></label>` : ""}
    </div>`;
  }

  setCoverWiring(value) {
    const d = this._state.draft;
    this._state.coverWiring = { id: d.id, value };
    if (!value.startsWith("relay")) d.options.power_entity = null;
    if (!value.endsWith("wall")) d.options.switch_entity = d.options.switch_close_entity = null;
    this.dirty();
    this.render();
  }

  // ---------- covers: timing a full travel ----------
  coverEntity(d) {
    const saved = this._state.devices.find((x) => x.id === d.id);
    return (saved?.entities || []).find((e) => e.startsWith("cover."));
  }

  renderMeasure(d) {
    const m = this._state.measure;
    if (m) {
      return `<div class="full measure"><b>${this.t(m.dir === "open" ? "measure_opening" : "measure_closing")}</b>
        <span id="measure-clock" class="clock">0.0 s</span>
        <div class="actions"><button class="primary" data-action="measure-stop">■ ${this.t("measure_arrived")}</button>
        <button data-action="measure-cancel">${this.t("measure_cancel")}</button></div>
        <small>${this.t(d.options.state_entity ? "measure_running_meter" : "measure_running")}</small></div>`;
    }
    if (!this.coverEntity(d) || !d.commands.open || !d.commands.close) {
      return `<small class="full">⏱ ${this.t("measure_save_first")}</small>`;
    }
    return `<div class="full measure"><b>⏱ ${this.t("measure_title")}</b>
      <div class="actions"><button data-action="measure" data-dir="open">▲ ${this.t("measure_open")}</button>
      <button data-action="measure" data-dir="close">▼ ${this.t("measure_close")}</button></div>
      <small>${this.t("measure_help")}</small></div>`;
  }

  async startMeasure(dir) {
    const d = this._state.draft;
    const eid = this.coverEntity(d);
    if (!eid || this._state.measure) return;
    try {
      await this._hass.callService("cover", dir === "open" ? "open_cover" : "close_cover", { entity_id: eid });
    } catch (e) {
      return this.toast(e.message, true);
    }
    const m = (this._state.measure = { dir, eid, id: d.id, start: performance.now(), seen: false, last: 0 });
    this.render();
    m.timer = setInterval(() => {
      const now = performance.now();
      const clock = this.shadowRoot.getElementById("measure-clock");
      if (clock) clock.textContent = `${((now - m.start) / 1000).toFixed(1)} s`;
      // With a meter the motor itself says when it arrived.
      const o = this._state.draft?.options || {};
      const st = o.state_entity && this._hass.states[o.state_entity];
      if (!st) return;
      const running = st.state === "on" || Number(st.state) > (o.state_threshold ?? 3);
      if (running) Object.assign(m, { seen: true, last: now });
      else if (m.seen && now - m.last > 1500) this.stopMeasure(true, (m.last - m.start) / 1000);
    }, 100);
  }

  async stopMeasure(keep, seconds = null) {
    const m = this._state.measure;
    if (!m) return;
    clearInterval(m.timer);
    this._state.measure = null;
    const d = this._state.draft;
    try {
      if (!keep) {
        if (d?.commands.stop) await this._hass.callService("cover", "stop_cover", { entity_id: m.eid });
      } else if (d && d.id === m.id) {
        const elapsed = seconds ?? (performance.now() - m.start) / 1000;
        d.options[m.dir === "open" ? "open_time" : "close_time"] = Math.min(300, Math.max(0.1, Math.round(elapsed * 10) / 10));
        // It is at the end of its travel now, whatever the old times said.
        await this._hass.callService("rf_devices", "set_position_state", { entity_id: m.eid, position: m.dir === "open" ? 100 : 0 });
        this.dirty();
      }
    } catch (e) {
      this.toast(e.message, true);
    }
    this.render();
  }

  renderRelay(d) {
    if (d.type === "cover") return this.renderCoverRelay(d);
    const o = d.options;
    const on = this.relayOn(d);
    const mode = this.relayMode(d);
    const info = this._state.relayInfo && this._state.relayInfo.relay === o.power_entity ? this._state.relayInfo.data : null;
    const caps = info?.capabilities || {};
    const DEFAULT_ON = { power_up_check: true, ensure_light_on_power_up: true }; // on by default in the backend
    const check = (opt, label, help, extra = "") =>
      `<label class="check full"><input type="checkbox" data-opt="${opt}" data-rerender="1" ${(o[opt] ?? DEFAULT_ON[opt]) ? "checked" : ""} ${extra}> ${label}</label>${help ? `<small class="full">${help}</small>` : ""}`;
    const isFeedback = (e, st) =>
      /^(binary_sensor|input_boolean|switch|light)\./.test(e) || (/^sensor\./.test(e) && st.attributes.unit_of_measurement === "W");
    const meterKey = d.type === "fan" ? "light_state_entity" : "state_entity";
    const wallDisabled = info && o.switch_entity && o.switch_entity === info.suggested_input && info.input_disabled;
    let body = `<div class="form">
      <label class="full">${this.t("relay_q")}
        <select data-opt="relay_mode" data-rerender="1">
          <option value="none" ${mode === "none" ? "selected" : ""}>${this.t("relay_no")}</option>
          <option value="coupled" ${on ? "selected" : ""}>${this.t("relay_yes")}</option>
          <option value="wall_only" ${mode === "wall_only" ? "selected" : ""}>${this.t("relay_wall_only")}</option>
        </select></label></div>`;
    if (mode === "wall_only") {
      const inputs = (e) => /^(binary_sensor|input_boolean|switch)\./.test(e);
      return body + this.diagram(d) + `<div class="form">
        ${this.entitySelect("switch_entity", this.t("wall_input"), inputs, this.t("wall_only_help"))}
        ${this.gesturesBlock(d)}
      </div>`;
    }
    if (!on) return body;
    body += this.diagram(d) + `<div class="form">
      ${this.entitySelect("power_entity", this.t("relay_entity"), (e) => /^(switch|light)\./.test(e))}
      ${info ? `<small class="full">${esc(this.t("relay_detected", { label: info.label }))}${(caps.notes || []).map((n) => `<br>${esc(this.t("note_" + n))}`).join("")}</small>` : ""}
      <label class="full">${this.t("relay_mode")}
        <select data-opt="relay_mode" data-rerender="1">
          <option value="coupled" ${mode === "coupled" ? "selected" : ""}>${this.t("mode_a")}</option>
          <option value="detached" ${mode === "detached" ? "selected" : ""}>${this.t("mode_b")}</option>
        </select><small>${mode === "detached" ? this.t("mode_b_help") : this.t("mode_a_help")}</small></label>
      ${mode === "detached"
        ? this.entitySelect("switch_entity", this.t("wall_input"), (e) => /^(binary_sensor|input_boolean|switch)\./.test(e) || (info && e === info.suggested_input),
            wallDisabled ? this.t("wall_input_disabled") : "", info ? [info.suggested_input] : [])
        : ""}
      ${this.entitySelect(meterKey, this.t("meter_entity"), isFeedback)}
      ${this.hasLight(d) && o[meterKey] ? check("ensure_light_on_power_up", this.t("ensure_light_on"), this.t("ensure_light_on_help")) : ""}
      ${d.type === "fan" ? check("fan_power_on", this.t("fan_power_on"), this.t("fan_power_on_help")) : ""}
      ${d.type === "fan" && o.fan_power_on
        ? `<div class="full timeline"><b>${this.t("tl_title")}</b>
             <div class="tl"><span class="tl-step">🔌 ${this.t("tl_relay")}</span><span class="tl-wait">${this.fmt(o.power_up_delay ?? 0.5)} s</span>
             <span class="tl-step">💡 ${this.t("tl_light_off")}</span><span class="tl-wait">${this.fmt(o.power_up_gap ?? 0.4)} s</span>
             <span class="tl-step">🌀 ${this.t("tl_fan")}</span></div></div>
           <label>${this.t("power_up_delay")}<input class="dec" type="text" inputmode="decimal" data-min="0" data-max="15" data-opt="power_up_delay" data-rerender="1" value="${this.fmt(o.power_up_delay ?? 0.5)}"><small>${this.t("power_up_delay_help")}</small></label>
           ${o[meterKey] ? check("power_up_wait_meter", this.t("power_up_wait_meter"), "") : ""}
           <label>${this.t("power_up_gap")}<input class="dec" type="text" inputmode="decimal" data-min="0" data-max="5" data-opt="power_up_gap" data-rerender="1" value="${this.fmt(o.power_up_gap ?? 0.4)}"></label>
           ${o[meterKey] ? check("power_up_check", this.t("power_up_check"), this.t("power_up_check_help")) : ""}`
        : ""}
      ${mode === "detached" ? this.gesturesBlock(d) : ""}
      ${mode === "detached" && caps.fallback_script ? check("fallback_script", this.t("fallback_script"), this.t("fallback_help")) : ""}
      ${mode === "detached" && caps.fallback_script && o.fallback_script
        ? `<label>${this.t("fallback_wait")}<input class="dec" type="text" inputmode="decimal" data-min="0.5" data-max="10" data-opt="fallback_wait" value="${this.fmt(o.fallback_wait ?? 2)}"></label>`
        : ""}
      ${check("take_relay_name", this.t("take_relay_name"), this.t("take_relay_name_help"))}
      ${o.take_relay_name ? check("take_relay_entity_id", this.t("take_relay_entity_id"), this.t("take_relay_entity_id_help")) : ""}
      ${check("hide_sources", this.t("hide_sources"), this.t("hide_help"))}
      <h3 class="full">${this.t("idle_title")}</h3>
      <label>${this.t("idle_minutes")}<input type="number" min="0" max="1440" step="5" data-opt="idle_off_minutes" data-rerender="1" value="${o.idle_off_minutes ?? 0}"></label>
      ${o.idle_off_minutes
        ? `<label>${this.t("idle_when")}<select data-opt="idle_off_when" data-rerender="1">
             <option value="always" ${(o.idle_off_when || "always") === "always" ? "selected" : ""}>${this.t("idle_always")}</option>
             <option value="night" ${o.idle_off_when === "night" ? "selected" : ""}>${this.t("idle_night")}</option>
             <option value="hours" ${o.idle_off_when === "hours" ? "selected" : ""}>${this.t("idle_hours")}</option></select></label>
           ${o.idle_off_when === "hours"
             ? `<label>${this.t("idle_from")}<input type="time" data-opt="idle_off_from" value="${o.idle_off_from || "23:00"}"></label>
                <label>${this.t("idle_to")}<input type="time" data-opt="idle_off_to" value="${o.idle_off_to || "08:00"}"></label>`
             : ""}`
        : ""}
      <small class="full">${this.t("idle_help")}</small>
      </div>
      <div class="actions"><span class="spacer"></span><button data-action="relay-apply">⚙ ${this.t("apply_relay")}</button></div>`;
    return body;
  }

  async loadRelayInfo() {
    const relay = this._state.draft?.options?.power_entity;
    if (!relay || this._state.relayInfo?.relay === relay) return;
    this._state.relayInfo = { relay, data: null };
    try {
      const data = await this.ws({ type: "rf_devices/relay/info", relay });
      this._state.relayInfo = { relay, data };
      const o = this._state.draft.options;
      const meterKey = this._state.draft.type === "fan" ? "light_state_entity" : "state_entity";
      if (!o[meterKey] && data.suggested_meter) o[meterKey] = data.suggested_meter;
      if (!o.switch_entity && data.suggested_input) o.switch_entity = data.suggested_input;
      this.render();
    } catch (e) {
      this._state.relayInfo = { relay, data: null };
    }
  }

  async applyRelay() {
    const d = this._state.draft;
    if (!this.isSaved()) return this.toast(this.t("save_first_relay"), true);
    if (!confirm(this.t("apply_confirm"))) return;
    if (!(await this.persist())) return; // apply what is on screen
    try {
      const r = await this.ws({ type: "rf_devices/relay/apply", device_id: d.id });
      this.toast(r.done.length ? this.t("applied", { list: r.done.join(", ") }) : this.t("nothing_to_apply"));
      this._state.relayInfo = null;
      this.loadRelayInfo();
    } catch (e) {
      this.toast(e.message, true);
    }
  }

  gestureActions(d) {
    const o = d.options;
    if (o.wall_actions) return o.wall_actions;
    return { 1: this.hasLight(d) ? "light_toggle" : "fan_toggle" };
  }

  gesturesBlock(d) {
    const o = d.options;
    const fan = d.type === "fan";
    const acts = ["none"];
    if (this.hasLight(d)) acts.push("light_toggle", "light_on", "light_off");
    if (this.hasLight(d) && d.commands.light_color) acts.push("light_color");
    if (fan) acts.push("fan_step", "fan_up", "fan_down", "fan_toggle", "fan_on", "fan_off");
    if (fan && o.direction && o.direction !== "none") acts.push("fan_direction");
    acts.push("all_off");
    if (this.relayMode(d) === "detached") acts.push("power_off");
    const table = this.gestureActions(d);
    const window = o.wall_window ?? 0.6;
    const rows = [1, 2, 3, 4].map((n) => `<label>${n === 4 ? this.t("gesture_4") : this.t("gesture_n", { n })}
        <select data-gesture="${n}">${acts.map((a) => `<option value="${a}" ${(table[n] || "none") === a ? "selected" : ""}>${this.t("ga_" + a)}</option>`).join("")}</select></label>`).join("");
    return `<h3 class="full">${this.t("gestures_title")}</h3>
      <small class="full">${this.t("gestures_help")}</small>
      ${rows}
      <label>${this.t("gesture_window")}<input class="dec" type="text" inputmode="decimal" data-min="0.2" data-max="2" data-opt="wall_window" value="${this.fmt(window)}"></label>`;
  }

  /** One remote, possibly two devices in HA: "Terrace fan + Terrace light". */
  remoteTitle(d) {
    return d.type === "fan" && this.hasLight(d) && d.options.light_name ? `${d.name} + ${d.options.light_name}` : d.name;
  }

  remoteKind(d) {
    return d.type === "fan" && this.hasLight(d) ? this.t("t_fan_light") : this.t("t_" + d.type);
  }

  /** Open a page of Home Assistant (e.g. a device page) inside the frontend. */
  navigate(path) {
    history.pushState(null, "", path);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  }

  hasLight(d) {
    return d.type === "light" || (d.type === "fan" && d.options.light && d.options.light !== "none");
  }

  renderGeneral(d) {
    const o = d.options;
    const info = this._state.info;
    const txName = (id) => info.transmitters.find((t) => t.entity_id === id)?.name || id;
    const sel = (opt, choices) => `<select data-opt="${opt}" data-rerender="1">
        ${choices.map(([v, l]) => `<option value="${v}" ${o[opt] === v ? "selected" : ""}>${l}</option>`).join("")}</select>`;
    let extra = "";
    if (d.type === "light" || d.type === "switch") {
      extra = `<label>${this.t("mode")}${sel("mode", [["toggle", this.t("mode_toggle")], ["onoff", this.t("mode_onoff")]])}</label>
        ${this.relayMode(d) !== "none" ? "" : this.entitySelect("switch_entity", this.t("switch_entity"), (e) => /^(binary_sensor|input_boolean|switch)\./.test(e), this.t("switch_entity_help"))}`;
    } else if (d.type === "cover") {
      extra = `
        <label>${this.t("open_time")}<input class="dec" type="text" inputmode="decimal" data-min="0" data-max="300" data-opt="open_time" value="${this.fmt(o.open_time ?? 0)}"></label>
        <label>${this.t("close_time")}<input class="dec" type="text" inputmode="decimal" data-min="0" data-max="300" data-opt="close_time" value="${this.fmt(o.close_time ?? 0)}"></label>
        <label>${this.t("device_class")}<select data-opt="device_class">
          ${COVER_CLASSES.map((c) => `<option ${o.device_class === c ? "selected" : ""}>${c}</option>`).join("")}</select></label>
        <small class="full">${this.t("times_help")}</small>
        ${this.renderMeasure(d)}`;
    } else if (d.type === "fan") {
      extra = `
        <label>${this.t("fan_power")}${sel("power", [["off", this.t("power_off_button")], ["toggle", this.t("power_toggle")]])}</label>
        <label>${this.t("speeds")}<input type="number" min="1" max="${info.max_speeds}" data-opt="speeds" data-rerender="1" value="${o.speeds ?? 3}"></label>
        <label>${this.t("turn_on_speed")}<select data-opt="turn_on_speed" data-num="1">
          <option value="0" ${o.turn_on_speed === 0 ? "selected" : ""}>${this.t("turn_on_last")}</option>
          ${Array.from({ length: o.speeds ?? 3 }, (_, i) => `<option value="${i + 1}" ${(o.turn_on_speed ?? 1) === i + 1 ? "selected" : ""}>${this.t("speed_word")} ${i + 1}</option>`).join("")}
        </select><small>${this.t("turn_on_speed_help")}</small></label>
        <label>${this.t("direction")}${sel("direction", [["none", this.t("none")], ["toggle", this.t("dir_toggle")], ["buttons", this.t("dir_buttons")]])}</label>
        <label>${this.t("presets")}<input data-opt="presets" data-list="1" data-rerender="1" value="${esc((o.presets || []).join(", "))}" placeholder="Brisa"><small>${this.t("presets_help")}</small></label>
        <label>${this.t("timers")}<input data-opt="timers" data-list="1" data-rerender="1" value="${esc((o.timers || []).join(", "))}" placeholder="1H, 2H, 4H, 8H"><small>${this.t("timers_help")}</small></label>
        <label class="check full"><input type="checkbox" data-has-light="1" ${o.light && o.light !== "none" ? "checked" : ""}> ${this.t("has_light")}</label>
        ${o.light && o.light !== "none"
          ? `<label>${this.t("fan_light")}${sel("light", [["toggle", this.t("mode_toggle")], ["onoff", this.t("mode_onoff")]])}</label>`
          : ""}`;
    }
    return `<div class="form">
      <label>${this.t("name")}<input id="name" data-field="name" value="${esc(d.name)}" placeholder="Luz cama"></label>
      <label>${this.t("type")}<select data-action="type">
        ${info.device_types.map((t) => `<option value="${t}" ${d.type === t ? "selected" : ""}>${TYPE_ICONS[t]} ${this.t("t_" + t)}</option>`).join("")}
      </select></label>
      <label>${this.t("transmitter")}<select data-field="transmitter">
        <option value="">${esc(this.t("default_tx", { name: txName(info.default_transmitter) }))}</option>
        ${info.transmitters.map((t) => `<option value="${t.entity_id}" ${d.transmitter === t.entity_id ? "selected" : ""}>${esc(t.name)} (${t.entity_id})</option>`).join("")}
      </select></label>
      ${extra}
      <label>${this.t("command_interval")}<input class="dec" type="text" inputmode="decimal" data-min="0" data-max="5" data-field-num="command_interval"
        value="${this.fmt(d.command_interval ?? "")}" placeholder="${this.fmt(info.min_interval ?? 0.4)}">
        <small>${this.t("command_interval_help", { g: info.min_interval ?? 0.4 })}</small></label>
    </div>
    ${this.renderControl(d)}`;
  }

  renderLightTab(d) {
    const o = d.options;
    return `<div class="form">
      ${d.type === "fan" ? `<label>${this.t("light_name")}<input data-opt="light_name" data-null="1" value="${esc(o.light_name || "")}" placeholder="${esc(this.defaultLightName())}"></label>` : ""}
      ${this.lightExtras()}
    </div>`;
  }

  renderPowerTab(d) {
    const meter = d.type === "fan"
      ? (this.relayOn(d) ? "" : this.feedbackFields("light_state_entity", "light_state_threshold", this.t("light_feedback")))
      : (this.relayOn(d) ? "" : this.feedbackFields("state_entity", "state_threshold", this.t("feedback")));
    return `<div class="form">${meter}${d.type === "fan" && this.hasLight(d) ? this.calibrationBlock() : ""}
      ${d.type === "fan" ? this.percentTable(d) : ""}</div>
      <div class="lives" data-live="draft">${this.liveInfo(d)}</div>`;
  }

  evenPercents(n) {
    return Array.from({ length: n }, (_, i) => Math.floor(((i + 1) * 100) / n)); // as Home Assistant
  }

  percentTable(d) {
    const o = d.options;
    const n = o.speeds ?? 3;
    const custom = o.speed_percentages || [];
    const table = custom.length === n ? custom : this.evenPercents(n);
    const small = o.small_pct_is_speed ?? true;
    let from = 1;
    const rows = table.map((pct, i) => {
      const row = `<tr><td>${this.t("speed_word")} ${i + 1}</td><td>${from}–</td>
        <td><input class="calcell" type="number" min="1" max="100" data-pct="${i}" value="${pct}"> %</td></tr>`;
      from = pct + 1;
      return row;
    }).join("");
    return `<div class="full calblock"><b>${this.t("pct_title")}</b><small class="full">${this.t("pct_help")}</small>
      <table class="cal">${rows}</table>
      <label class="check full"><input type="checkbox" data-opt="small_pct_is_speed" ${small ? "checked" : ""}> ${this.t("pct_small")}</label>
      <div class="actions"><button data-action="pct-reset">${this.t("pct_reset")}</button></div></div>`;
  }

  tabs(d) {
    const t = [["general", "⚙", "tab_general"], ["buttons", "🎛", "tab_buttons"]];
    if (this.hasLight(d)) t.push(["light", "💡", "tab_light"]);
    if (["light", "switch", "fan"].includes(d.type)) t.push(["relay", "🔌", "tab_relay"], ["power", "⚡", "tab_power"]);
    if (d.type === "cover") t.push(["relay", "🔌", "tab_relay"]);
    t.push(["live", "▶", "tab_live"]);
    return t;
  }

  /** Control cards for the device's own entities and its relay, for testing. */
  renderLive() {
    const d = this._state.draft;
    const saved = this._state.devices.find((x) => x.id === d?.id);
    if (!saved) return `<p class="sub">${this.t("live_save_first")}</p>`;
    const st = this._hass.states;
    const onoff = (s) => (s === "on" ? this.t("on_word") : s === "off" ? this.t("off_word") : s ?? "—");
    const toggle = (eid, on) =>
      `<button class="tgl ${on ? "on" : ""}" data-svc="homeassistant.toggle" data-eid="${eid}" aria-pressed="${on}"><span></span></button>`;
    const card = (icon, name, state, body = "", right = "") =>
      `<div class="lcard"><div class="lhead"><span class="licon">${icon}</span><div class="lname">${esc(name)}<div class="sub">${esc(state)}</div></div>${right}</div>${body}</div>`;
    const links = (saved.ha_devices || []).map((dev) =>
      `<button class="link" data-open-device="${esc(dev.id)}">↗ ${esc(dev.name)}</button>`).join("");
    const devLinks = links ? `<div class="devlinks"><b>${this.t("ha_devices")}</b>${links}<small>${this.t("open_device_help")}</small></div>` : "";
    const cards = [];
    const lightCards = [];
    const lightSet = new Set(saved.light_entities || []);
    for (const eid of saved.entities || []) {
      const s = st[eid];
      if (!s) continue;
      const bucket = lightSet.has(eid) ? lightCards : cards;
      const a = s.attributes;
      const name = a.friendly_name || eid;
      const [dom] = eid.split(".");
      if (dom === "light") {
        let body = "";
        if (a.supported_color_modes?.includes("color_temp") && s.state === "on" && a.min_color_temp_kelvin) {
          body += `<label class="lrow">${this.t("color_kelvin")}: ${a.color_temp_kelvin ?? "—"} K</label>`;
        }
        if (a.supported_color_modes?.some((m) => m === "brightness" || m === "color_temp") && s.state === "on") {
          body += `<label class="lrow">${this.t("brightness")} ${Math.round(((a.brightness ?? 255) / 255) * 100)}%
            <input type="range" min="1" max="100" value="${Math.round(((a.brightness ?? 255) / 255) * 100)}" data-svc="light.turn_on" data-eid="${eid}" data-param="brightness_pct"></label>`;
        }
        bucket.push(card("💡", name, onoff(s.state), body, toggle(eid, s.state === "on")));
      } else if (dom === "fan") {
        const table = a.speed_percentages ||
          Array.from({ length: Math.round(100 / (a.percentage_step || 100)) }, (_, i) => Math.floor(((i + 1) * 100) / Math.round(100 / (a.percentage_step || 100))));
        const cur = a.percentage ? table.findIndex((p) => a.percentage <= p) + 1 : 0;
        let body = `<div class="chips">${table.map((pct, i) =>
          `<button class="chipbtn ${cur === i + 1 ? "on" : ""}" data-svc="fan.set_percentage" data-eid="${eid}" data-json='{"percentage":${pct}}'>${i + 1}</button>`).join("")}</div>`;
        if (a.direction) {
          body += `<div class="chips">${["forward", "reverse"].map((dir) =>
            `<button class="chipbtn ${a.direction === dir ? "on" : ""}" data-svc="fan.set_direction" data-eid="${eid}" data-json='{"direction":"${dir}"}'>${this.t(dir)}</button>`).join("")}</div>`;
        }
        if (a.preset_modes?.length) {
          body += `<div class="chips">${a.preset_modes.map((p) =>
            `<button class="chipbtn ${a.preset_mode === p ? "on" : ""}" data-svc="fan.set_preset_mode" data-eid="${eid}" data-json='${esc(JSON.stringify({ preset_mode: p }))}'>${esc(p)}</button>`).join("")}</div>`;
        }
        bucket.push(card("🌀", name, s.state === "on" ? `${this.t("speed_word")} ${cur}` : onoff(s.state), body, toggle(eid, s.state === "on")));
      } else if (dom === "select") {
        const syncing = !!this._state.syncColor?.[eid];
        const svc = syncing ? "rf_devices.set_color_mode" : "select.select_option";
        bucket.push(card("🎨", name, s.state,
          `<div class="chips">${(a.options || []).map((o) =>
            `<button class="chipbtn ${s.state === o ? "on" : ""} ${syncing ? "sync" : ""}" data-svc="${svc}" data-eid="${eid}" data-json='${esc(JSON.stringify({ option: o }))}'>${esc(o)}</button>`).join("")}</div>
           <label class="check synccheck" title="${esc(this.t("sync_no_send_help"))}"><input type="checkbox" data-sync-color="${eid}" ${syncing ? "checked" : ""}> ${this.t("sync_no_send")}</label>
           ${syncing ? `<small class="sub">${this.t("sync_no_send_help")}</small>` : ""}`));
      } else if (dom === "switch") {
        bucket.push(card("🔌", name, onoff(s.state), "", toggle(eid, s.state === "on")));
      } else if (dom === "cover") {
        bucket.push(card("🪟", name, s.state, `<div class="chips">
          <button class="chipbtn" data-svc="cover.open_cover" data-eid="${eid}">▲</button>
          <button class="chipbtn" data-svc="cover.stop_cover" data-eid="${eid}">■</button>
          <button class="chipbtn" data-svc="cover.close_cover" data-eid="${eid}">▼</button></div>`));
      } else if (dom === "button") {
        bucket.push(card("🔘", name, "", "", `<button class="chipbtn" data-svc="button.press" data-eid="${eid}">${this.t("press")}</button>`));
      } else if (dom === "sensor") {
        bucket.push(card("⚡", name, `${s.state} ${a.unit_of_measurement || ""}`));
      } else if (dom === "binary_sensor") {
        bucket.push(card("🔌", name, onoff(s.state)));
      }
    }
    const relayCards = [];
    const o = saved.options;
    if (this.relayOn(saved)) {
      const r = st[o.power_entity];
      if (r) relayCards.push(card("🔌", `${this.t("relay_state")} · ${r.attributes.friendly_name || o.power_entity}`, onoff(r.state), "", toggle(o.power_entity, r.state === "on")));
      const w = o.switch_entity && st[o.switch_entity];
      if (w) relayCards.push(card("🔘", `${this.t("wall_state")} · ${w.attributes.friendly_name || o.switch_entity}`, onoff(w.state)));
      const meter = o.light_state_entity || o.state_entity;
      const m = meter && st[meter];
      if (m) {
        const lv = this._live?.entity === meter && this._live.watts !== undefined ? this._live : null;
        const value = lv ? `${this.fmt(lv.watts)} ${m.attributes.unit_of_measurement || "W"}` : `${m.state} ${m.attributes.unit_of_measurement || ""}`;
        relayCards.push(card("⚡", `${this.t("meter_state")} · ${m.attributes.friendly_name || meter}`,
          value, "", lv?.direct ? `<span class="badge">● ${this.t("live_badge")}</span>` : ""));
      }
    }
    const reloading = this._reloadedAt && Date.now() - this._reloadedAt < 2500;
    return `${reloading ? `<p class="sub">${this.t("live_reloading")}</p>` : ""}
      ${devLinks}
      ${lightCards.length
        ? `<h3>🌀 ${this.t("group_fan")}</h3>${cards.join("")}<h3>💡 ${this.t("group_light")}</h3>${lightCards.join("")}`
        : `<h3>${this.t("live_rf")}</h3>${cards.join("") || "<p class='sub'>—</p>"}`}
      ${relayCards.length ? `<h3>${this.t("live_relay_group")}</h3>${relayCards.join("")}` : ""}`;
  }

  async _liveAction(el) {
    const [domain, service] = el.dataset.svc.split(".");
    const data = { entity_id: el.dataset.eid, ...(el.dataset.json ? JSON.parse(el.dataset.json) : {}) };
    if (el.dataset.param) data[el.dataset.param] = Number(el.value);
    try {
      await this._hass.callService(domain, service, data);
    } catch (e) {
      this.toast(e.message, true);
    }
  }

  /** Remote buttons; a fan with a light shows the fan's and the light's apart. */
  renderSlots(d) {
    const slots = slotsFor(d);
    if (d.type !== "fan" || !this.hasLight(d)) return this.renderSlotList(d, slots);
    const light = slots.filter((x) => x.role.startsWith("light_"));
    const fan = slots.filter((x) => !x.role.startsWith("light_"));
    return `<h3>🌀 ${this.t("group_fan")}</h3>${this.renderSlotList(d, fan)}
      <h3>💡 ${this.t("group_light")}</h3>${this.renderSlotList(d, light)}`;
  }

  renderSlotList(d, slots) {
    const byFp = {};
    for (const [role, c] of Object.entries(d.commands)) if (c.fingerprint) (byFp[c.fingerprint] ||= []).push(role);
    return slots
      .map(({ role, required }) => {
        const c = d.commands[role];
        const has = hasCode(c);
        const kind = has ? c.kind || "rf" : null;
        const a = kind === "rf" ? c.analysis : null;
        const dup = has && c.fingerprint ? byFp[c.fingerprint].filter((r) => r !== role) : [];
        const warnings = [];
        if (a?.needs_cleaning) warnings.push(this.t("needs_cleaning", { frames: a.frames, times: this.times(a.repeat), ms: a.sent_ms }));
        if (dup.length) warnings.push(this.t("duplicate", { other: dup.map((r) => this.roleLabel(r, d)).join(", ") }));
        const info = !has ? this.t("not_learned")
          : kind === "somfy" ? this.t("kind_somfy", { b: this.t("b_" + c.button) })
          : kind === "action" ? this.t("kind_action", { svc: `${c.service}${c.entity_id ? ` → ${c.entity_id}` : ""}${Object.keys(c.data || {}).length ? ` ${JSON.stringify(c.data)}` : ""}` })
          : [c.frequency ? this.t("frequency", { f: c.frequency }) : null, a ? `${a.kind.toUpperCase()} · ${this.t("frames_info", { good: a.good_frames, ms: a.sent_ms })}` : null]
              .filter(Boolean)
              .join(" · ");
        return `<div class="slot ${has ? "done" : required ? "todo" : "opt"}">
          <div class="slot-main">
            <div class="slot-name">${esc(this.roleLabel(role, d))}${required ? "" : ` <small>(${this.t("optional")})</small>`}</div>
            <div class="sub">${esc(info)}</div>
            ${warnings.map((w) => `<div class="warn-text">⚠ ${esc(w)}</div>`).join("")}
            ${has && (role.startsWith("x_") || role === "light_up" || role === "light_down") ? `<label class="hold" title="${esc(this.t("hold_help"))}">${this.t("hold")}
              <input class="dec" type="text" inputmode="decimal" data-min="0" data-max="10" data-hold="${role}" value="${this.fmt(c.hold || (role.startsWith("light_") ? 0.5 : 0))}"></label>` : ""}
          </div>
          ${a ? this.wave(a.sample_us, a.frame_map) : ""}
          <div class="slot-actions">
            ${kind === "somfy"
              ? `<select data-action="somfy-btn" data-role="${role}" title="${esc(this.t("somfy_button"))}">${(this._state.info.somfy_buttons || []).map((b) =>
                  `<option value="${b}" ${c.button === b ? "selected" : ""}>${esc(this.t("b_" + b))}</option>`).join("")}</select>`
              : kind === "action"
                ? `<button class="primary" data-action="edit-action" data-role="${role}">${this.t("edit")}</button>`
                : `<button class="primary" data-action="learn" data-role="${role}">${this.t("learn")}</button>`}
            ${has ? `<button data-action="test" data-role="${role}">${this.t("test")}</button>` : ""}
            ${has && a && a.kind !== "ir" && a.good_frames >= 1
              ? `<label class="frames" title="${esc(this.t("frames_help"))}">${this.t("frames_label")}
                  <select data-frames="${role}">${[1, 2, 3, 4, 5, 6, 8].map((n) =>
                    `<option ${n === a.good_frames ? "selected" : ""}>${n}</option>`).join("")}</select></label>`
              : ""}
            <select data-action="more" data-role="${role}">
              <option value="">${this.t("more")}…</option>
              <option value="paste">${this.t("paste")}</option>
              <option value="device">${this.t("from_device")}</option>
              <option value="broadlink">${this.t("from_broadlink")}</option>
              <option value="action">${this.t("more_action")}</option>
              ${d.somfy ? `<option value="somfy">${this.t("more_somfy")}</option>` : ""}
              ${kind === "rf" ? `<option value="copy">${this.t("copy_code")}</option>` : ""}
              ${kind === "rf" ? `<option value="clean">${this.t("clean")}</option>` : ""}
              ${has || role.startsWith("x_") ? `<option value="remove">${this.t("remove")}</option>` : ""}
            </select>
          </div></div>`;
      })
      .join("");
  }

  renderEdit() {
    const d = this._state.draft;
    const tabs = this.tabs(d);
    let tab = this._state.tab || "general";
    if (!tabs.some(([k]) => k === tab)) tab = "general";
    const saved = this.isSaved();
    const body =
      tab === "buttons" ? `${this.renderSlots(d)}
          <div class="add-extra"><input id="extra-name" placeholder="${this.t("button_name")}">
            <button data-action="add-extra">＋ ${this.t("add_button")}</button></div>`
      : tab === "light" ? this.renderLightTab(d)
      : tab === "relay" ? this.renderRelay(d)
      : tab === "power" ? this.renderPowerTab(d)
      : tab === "live" ? `<div class="live-inline" id="live-inline">${this.renderLive()}</div>`
      : this.renderGeneral(d);
    const st = this._state.saveStatus || "saved";
    return `
      <div class="edit-head">
        <button data-action="back">←</button>
        <div class="edit-title"><span class="icon">${TYPE_ICONS[d.type] || "📡"}</span>${esc(d.name ? this.remoteTitle(d) : this.t("new_device"))}</div>
        <span class="spacer"></span>
        ${saved ? `<span id="save-status" class="save-status ${st}">${this.t("st_" + st)}</span>`
                : `<button class="primary" data-action="save">${this.t("create")}</button>`}
      </div>
      <nav class="tabs">${tabs.map(([k, icon, label]) =>
        `<button class="tab ${k === tab ? "on" : ""} ${k === "live" ? "tab-live" : ""}" data-action="tab" data-tab="${k}">${icon} ${this.t(label)}</button>`).join("")}</nav>
      <div class="edit-grid">
        <section class="edit-main">${body}</section>
        <aside class="live" id="live">
          <h2>▶ ${this.t("live_title")}</h2><div id="live-body">${this.renderLive()}</div>
        </aside>
      </div>`;
  }

  renderResult(r, withRaw = true, retry = false) {
    if (!r) return "";
    const differs = r.raw !== r.code;
    return `
      ${differs && withRaw ? `<div class="res"><b>${this.t("raw_capture")}</b><div class="sub">${this.summary(r.raw_analysis)}</div>${this.wave(r.raw_analysis.sample_us, r.raw_analysis.frame_map)}</div>` : ""}
      <div class="res"><b>${differs ? this.t("cleaned") : this.t("raw_capture")}</b><div class="sub">${this.summary(r.analysis)}</div>${this.wave(r.analysis.sample_us, r.analysis.frame_map)}
        <div class="sub mono">${r.analysis.kind.toUpperCase()} · ${r.analysis.bits.length} bits · 0x${r.analysis.hex}</div></div>
      <div class="actions">
        ${retry ? `<button data-action="start-learn">${this.t("retry")}</button>` : ""}
        <button data-action="test-code" data-which="code">${differs ? this.t("test_clean") : this.t("test")}</button>
        ${differs ? `<button data-action="test-code" data-which="raw">${this.t("test_raw")}</button>` : ""}
        <span class="spacer"></span>
        ${differs ? `<button data-action="use" data-which="raw">${this.t("use_raw")}</button>` : ""}
        <button class="primary" data-action="use" data-which="code">${differs ? this.t("use_clean") : this.t("use")}</button>
      </div>`;
  }

  renderDialog() {
    const dlg = this._state.dialog;
    if (!dlg) return "";
    const role = dlg.role ? this.roleLabel(dlg.role, this._state.draft) : "";
    let body = "";
    let title = "";
    if (dlg.kind === "learn") {
      title = dlg.somfyDetect ? this.t("follow_somfy_title") : this.t("learn_title", { role });
      const tx = this._state.info.transmitters.find((t) => t.entity_id === dlg.tx);
      const sweeps = tx?.sweeps ?? true;
      if (tx && !tx.can_learn) body = `<p class="warn-text">${esc(this.t("no_learn", { msg: tx.learn_problem || "" }))}</p>`;
      else if (dlg.stage === "idle") {
        body = `<p class="sub">${this.t(sweeps ? "capture_tip" : "capture_tip_rx")}</p>${dlg.knownFreq ? `<label class="check"><input type="checkbox" id="use-known" ${dlg.useKnown ? "checked" : ""}> ${this.t("known_freq", { f: dlg.knownFreq })}</label>` : ""}
          <div class="actions"><span class="spacer"></span><button class="primary" data-action="start-learn">${this.t("start")}</button></div>`;
      } else if (dlg.stage === "captured" && dlg.somfyDetect) {
        const found = new Map((dlg.somfy || []).map((p) => [p.address, p]));
        body = !dlg.somfy ? `<div class="stage busy"><div class="pulse"></div></div>`
          : found.size ? [...found.values()].map((p) => `<div class="bl-row"><span>${esc(this.t("follow_somfy_found", { hex: p.hex, b: this.t("b_" + p.button), c: p.rolling_code }))}</span>
              <button class="primary" data-action="follow-somfy" data-address="${p.address}">${this.t("follow_somfy_add")}</button></div>`).join("")
          : `<p class="warn-text">${this.t("follow_somfy_nothing")}</p><div class="actions"><span class="spacer"></span><button data-action="start-learn">${this.t("retry")}</button></div>`;
      } else if (dlg.stage === "captured") {
        body = this.renderResult(dlg.result, true, true);
      } else {
        let key = { starting: "st_starting", sweep: "st_sweep", frequency: "st_frequency", press: "st_press", timeout: "st_timeout", error: "st_error" }[dlg.stage];
        if (dlg.stage === "error" && dlg.reason === "unreachable") key = sweeps ? "st_unreachable" : "st_unreachable_rx";
        if (dlg.stage === "frequency" && !dlg.frequency) key = "st_found";
        const busy = ["starting", "sweep", "frequency", "press"].includes(dlg.stage);
        body = `<div class="stage ${busy ? "busy" : ""}">${busy ? '<div class="pulse"></div>' : ""}
            <p>${esc(this.t(key, { role, f: dlg.frequency ?? "", msg: dlg.message ?? "" }))}</p></div>
          ${busy ? "" : `<div class="actions"><span class="spacer"></span><button class="primary" data-action="start-learn">${this.t("retry")}</button></div>`}`;
      }
    } else if (dlg.kind === "action") {
      title = this.t("action_title", { role });
      const all = Object.keys(this._hass.states).sort();
      const dom = dlg.entity_id ? dlg.entity_id.split(".")[0] : null;
      const suggestions = [...new Set([...(SERVICES[dom] || []), ...Object.values(SERVICES).flat()])];
      body = `<div class="form">
          <label class="full">${this.t("action_service")}<input id="action-service" list="action-services" value="${esc(dlg.service)}" placeholder="cover.open_cover">
            <datalist id="action-services">${suggestions.map((x) => `<option value="${x}">`).join("")}</datalist></label>
          <label class="full">${this.t("action_entity")}<select id="action-entity"><option value="">${this.t("none")}</option>
            ${dlg.entity_id && !this._hass.states[dlg.entity_id] ? `<option value="${esc(dlg.entity_id)}" selected>${esc(dlg.entity_id)}</option>` : ""}
            ${all.map((e) => `<option value="${e}" ${dlg.entity_id === e ? "selected" : ""}>${esc(this._hass.states[e].attributes.friendly_name || e)} (${e})</option>`).join("")}</select></label>
          <label class="full">${this.t("action_data")}<textarea id="action-data" rows="3" placeholder='{"percentage": 50}'>${esc(dlg.data)}</textarea></label>
          <small class="full">${this.t("action_help")}</small>
        </div>
        ${dlg.message ? `<p class="warn-text">${esc(dlg.message)}</p>` : ""}
        <div class="actions"><button data-action="action-test">${this.t("test")}</button><span class="spacer"></span>
          <button class="primary" data-action="action-save">${this.t("use")}</button></div>`;
    } else if (dlg.kind === "paste") {
      title = `${this.t("paste_title")} — ${role}`;
      body = `<textarea id="paste-code" rows="4" placeholder="JgBQAAABKJIUEhQ…">${esc(dlg.result?.raw || "")}</textarea>
        ${dlg.message ? `<p class="warn-text">${esc(dlg.message)}</p>` : ""}
        <div class="actions"><span class="spacer"></span><button data-action="analyze">${this.t("analyze")}</button></div>
        ${this.renderResult(dlg.result)}`;
    } else if (dlg.kind === "calibrate") {
      title = this.t(dlg.lightOnly ? "calibrate_light" : "calibrate_title");
      const speeds = this._state.draft.options.speeds || 3;
      const lines = dlg.lines.map((l) => `<div class="${l.wait ? "sub" : ""}">${esc(l.wait || l.text)}</div>`).join("");
      if (dlg.stage === "idle")
        body = `<p>${this.t(dlg.lightOnly ? "calibrate_light_intro" : "calibrate_intro")}</p><p class="warn-text">${dlg.lightOnly ? this.t("calibrate_light_before") : this.t("calibrate_before", { min: Math.ceil((speeds * 2 * 130 + 60) / 60) })}</p>
          <div class="actions"><span class="spacer"></span><button class="primary" data-action="cal-start">${this.t("start")}</button></div>`;
      else if (dlg.stage === "running")
        body = `<div class="lives" data-live="draft">${this.liveInfo(this._state.draft)}</div>
          <div class="stage busy"><div class="pulse"></div><div class="cal-lines">${lines}</div></div>`;
      else if (dlg.stage === "done")
        body = `<div class="cal-lines">${lines}</div><p>${this.t(dlg.lightOnly ? "cal_light_done" : "cal_done")}</p>${dlg.lightOnly ? this.lampSummary(dlg.result) : this.calibrationTable(dlg.result)}
          <div class="actions"><span class="spacer"></span><button class="primary" data-action="cal-save">${this.t("cal_save")}</button></div>`;
      else
        body = `<div class="cal-lines">${lines}</div><p class="warn-text">${esc(this.t("st_error", { msg: dlg.message || "" }))}</p>
          <div class="actions"><span class="spacer"></span><button class="primary" data-action="cal-start">${this.t("retry")}</button></div>`;
    } else if (dlg.kind === "code") {
      title = this.t("code_title", { role });
      body = `<textarea rows="6" readonly id="code-view">b64:${esc(dlg.code)}</textarea>
        <div class="actions"><span class="spacer"></span><button class="primary" data-action="copy-again">${this.t("copy_code")}</button></div>`;
    } else if (dlg.kind === "devices") {
      title = `${this.t("devices_title")} — ${role}`;
      const rows = [];
      for (const dev of dlg.list)
        for (const [r, c] of Object.entries(dev.commands || {}))
          if (c.code)
            rows.push(`<div class="bl-row"><span><b>${esc(dev.name || "—")}</b> / ${esc(this.roleLabel(r, dev))}</span>
              <button data-action="bl-use" data-code="${esc(c.code)}">${this.t("use")}</button></div>`);
      body = rows.join("") || `<p>${this.t("bl_empty")}</p>`;
    } else if (dlg.kind === "broadlink") {
      title = `${this.t("bl_title")} — ${role}`;
      if (!dlg.codes) body = `<div class="stage busy"><div class="pulse"></div></div>`;
      else {
        const rows = [];
        for (const [file, devs] of Object.entries(dlg.codes))
          for (const [dev, cmds] of Object.entries(devs))
            for (const [cmd, code] of Object.entries(cmds))
              (Array.isArray(code) ? code : [code]).forEach((c, i) =>
                rows.push(`<div class="bl-row"><span><b>${esc(dev)}</b> / ${esc(cmd)}${Array.isArray(code) ? ` #${i + 1}` : ""}</span>
                  <button data-action="bl-use" data-code="${esc(c)}">${this.t("use")}</button></div>`)
              );
        body = rows.length ? rows.join("") : `<p>${this.t("bl_empty")}</p>`;
      }
    }
    return `<div class="overlay" data-action="overlay"><div class="dialog">
      <div class="dialog-head"><h2>${esc(title)}</h2><button class="icon-btn" data-action="close">✕</button></div>
      ${body}</div></div>`;
  }

  render() {
    if (!this._hass) return;
    const s = this._state;
    let main;
    if (s.error) main = `<div class="empty warn-text">${esc(s.error)}</div>`;
    else if (!s.info) main = `<div class="stage busy"><div class="pulse"></div></div>`;
    else main = s.view === "edit" ? this.renderEdit() : this.renderList();
    if (s.view === "edit" && s.draft && this.relayOn(s.draft)) queueMicrotask(() => this.loadRelayInfo());
    queueMicrotask(() => this._watchMeter());
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <header><button class="icon-btn menu" data-action="menu">☰</button><h1>${this.t("title")}</h1>
        ${s.info ? `<span class="ver">v${esc(s.info.version)}</span>` : ""}</header>
      <main>${main}</main>
      ${this.renderDialog()}
      ${s.toast ? `<div class="toast ${s.toast.error ? "err" : ""}">${esc(s.toast.text)}</div>` : ""}`;
    this._bind();
  }

  _bind() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-action]").forEach((el) => {
      const action = el.dataset.action;
      const ev = el.tagName === "SELECT" ? "change" : "click";
      el.addEventListener(ev, (e) => this._onAction(action, el, e));
    });
    for (const id of ["live", "live-inline"]) {
      const el = root.getElementById(id);
      if (!el) continue;
      el.addEventListener("click", (e) => {
        const dev = e.target.closest("[data-open-device]");
        if (dev) return this.navigate(`/config/devices/device/${dev.dataset.openDevice}`);
        const b = e.target.closest("[data-svc]");
        if (b && b.tagName === "BUTTON") this._liveAction(b);
      });
      el.addEventListener("change", (e) => {
        const sync = e.target.closest("[data-sync-color]");
        if (sync) {
          this._state.syncColor = { ...(this._state.syncColor || {}), [sync.dataset.syncColor]: sync.checked };
          this._refreshLive(true);
          return;
        }
        const b = e.target.closest("[data-svc]");
        if (b && b.tagName === "INPUT") this._liveAction(b);
      });
    }
    root.querySelectorAll("[data-field-num]").forEach((el) =>
      el.addEventListener("change", () => {
        this._state.draft[el.dataset.fieldNum] = this.num(el);
        this.dirty();
      })
    );
    root.querySelectorAll("[data-field]").forEach((el) =>
      el.addEventListener("input", () => {
        this._state.draft[el.dataset.field] = el.value || (el.dataset.field === "transmitter" ? null : "");
        this.dirty();
      })
    );
    root.querySelectorAll("[data-opt]").forEach((el) =>
      el.addEventListener("change", () => {
        const o = this._state.draft.options;
        let v = el.value;
        if (el.classList.contains("dec")) {
          v = this.num(el);
          if (v === null) return;
          el.value = this.fmt(v);
        } else if (el.type === "number" || el.dataset.num) v = Number(v);
        if (el.type === "checkbox") v = el.checked;
        if (el.dataset.null && !v) v = null;
        if (el.dataset.list) v = v.split(",").map((x) => x.trim()).filter(Boolean).slice(0, 6);
        if (el.dataset.nums) v = v.map(Number).filter((x) => x >= 1500 && x <= 10000);
        o[el.dataset.opt] = v;
        this.dirty();
        if (el.dataset.opt === "take_relay_name" && !v) o.take_relay_entity_id = false; // both go back
        if (el.dataset.opt === "light" && v !== "none" && !o.light_name) o.light_name = this.defaultLightName();
        if (el.dataset.opt === "power") {
          // The same physical button: keep its code when switching off-button <-> toggle.
          const cmds = this._state.draft.commands;
          const [from, to] = v === "toggle" ? ["off", "power"] : ["power", "off"];
          if (cmds[from] && !cmds[to]) {
            cmds[to] = cmds[from];
            delete cmds[from];
          }
        }
        if (el.dataset.rerender) this.render();
      })
    );
    root.querySelectorAll("[data-cal]").forEach((el) =>
      el.addEventListener("change", () => {
        const c = this._state.draft.options.calibration;
        const n = this.num(el);
        if (!c || n === null) return;
        const v = Math.round(n * 10) / 10;
        const [key, idx] = el.dataset.cal.split(".");
        if (key === "idle") c.idle = v;
        else if (key === "band_w") c.band_w = Math.max(0.1, v);
        else if (key === "band_pct") c.band_pct = Math.max(0.01, Math.min(1, n / 100));
        else if (key === "light_modes") {
          c.light_modes = c.light_modes || [c.light];
          c.light_modes[Number(idx)] = v;
          if (Number(idx) === 0) c.light = v;
        } else if (key === "speeds_down") {
          c.speeds_down = c.speeds_down || c.speeds.map((p) => p[0]);
          c.speeds_down[Number(idx)] = v;
        } else if (key === "speeds") {
          const lamp = (c.light_modes || [c.light])[0] - c.idle;
          c.speeds[Number(idx)] = [v, Math.round((v + lamp) * 10) / 10];
        }
        this.dirty();
        this.render();
      })
    );
    root.querySelectorAll("[data-frames]").forEach((el) =>
      el.addEventListener("change", async () => {
        const cmd = this._state.draft.commands[el.dataset.frames];
        try {
          cmd.source = cmd.source || cmd.code; // keep the original to go back up later
          const r = await this.ws({ type: "rf_devices/code/clean", code: cmd.source, frames: Number(el.value) });
          Object.assign(cmd, { code: r.code, analysis: r.analysis, fingerprint: r.fingerprint });
          this.dirty();
          this.render();
        } catch (e) {
          this.toast(e.message, true);
        }
      })
    );
    root.querySelectorAll("[data-cover-wiring]").forEach((el) =>
      el.addEventListener("change", () => this.setCoverWiring(el.value))
    );
    root.querySelectorAll("[data-has-light]").forEach((el) =>
      el.addEventListener("change", () => {
        const o = this._state.draft.options;
        o.light = el.checked ? (o.light && o.light !== "none" ? o.light : "toggle") : "none";
        if (el.checked && !o.light_name) o.light_name = this.defaultLightName();
        this.dirty();
        this.render();
      })
    );
    root.querySelectorAll("[data-gesture]").forEach((el) =>
      el.addEventListener("change", () => {
        const d = this._state.draft;
        const table = { ...this.gestureActions(d) };
        table[el.dataset.gesture] = el.value;
        const clean = {};
        for (const n of ["1", "2", "3", "4"]) if (table[n] && table[n] !== "none") clean[n] = table[n];
        if (d.options.wall_window === undefined) d.options.wall_window = 0.6;
        d.options.wall_actions = clean;
        this.dirty();
        this.render();
      })
    );
    root.querySelectorAll("[data-pct]").forEach((el) =>
      el.addEventListener("change", () => {
        const o = this._state.draft.options;
        const n = o.speeds ?? 3;
        const table = (o.speed_percentages?.length === n ? o.speed_percentages : this.evenPercents(n)).slice();
        const i = Number(el.dataset.pct);
        table[i] = Math.max(1, Math.min(100, Math.round(Number(String(el.value).replace(",", ".")) || table[i])));
        for (let k = i + 1; k < n; k++) table[k] = Math.max(table[k], table[k - 1] + 1); // keep ascending
        for (let k = i - 1; k >= 0; k--) table[k] = Math.min(table[k], table[k + 1] - 1);
        table[n - 1] = 100;
        o.speed_percentages = table;
        this.dirty();
        this.render();
      })
    );
    root.querySelectorAll("[data-somfy]").forEach((el) =>
      el.addEventListener("change", () => {
        const d = this._state.draft;
        const key = el.dataset.somfy;
        d.somfy = { ...d.somfy, [key]: el.type === "checkbox" ? el.checked : Math.max(0, Math.min(20, Number(el.value) || 0)) };
        this.dirty();
      })
    );
    root.querySelectorAll("[data-hold]").forEach((el) =>
      el.addEventListener("change", () => {
        this._state.draft.commands[el.dataset.hold].hold = this.num(el) ?? 0;
        this.dirty();
      })
    );
    const file = root.getElementById("import-file");
    if (file) file.addEventListener("change", () => file.files[0] && this.importFile(file.files[0]));
    const known = root.getElementById("use-known");
    if (known) known.addEventListener("change", () => (this._state.dialog.useKnown = known.checked));
  }

  _onAction(action, el, e) {
    const role = el.dataset.role;
    const dlg = this._state.dialog;
    switch (action) {
      case "menu":
        this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }));
        break;
      case "new": return this.newDevice();
      case "edit": return this.editDevice(el.dataset.id);
      case "delete": return this.deleteDevice(el.dataset.id);
      case "export": return this.exportAll();
      case "debug-report": return this.downloadDebug();
      case "import": return this.shadowRoot.getElementById("import-file").click();
      case "measure": return this.startMeasure(el.dataset.dir);
      case "measure-stop": return this.stopMeasure(true);
      case "measure-cancel": return this.stopMeasure(false);
      case "tab":
        this._state.tab = el.dataset.tab;
        return this.render();
      case "back":
        this.stopMeasure(false);
        if (this._state.saveStatus === "dirty") this.persist();
        this._state.view = "list";
        this._state.draft = null;
        return this.render();
      case "save": return this.saveDraft();
      case "type": return this.setType(el.value);
      case "learn": return this.openLearn(role);
      case "test": return this.testRole(role);
      case "control": return this.setControl(el.value);
      case "somfy-pair": return this.pairSomfy();
      case "somfy-new": return this.newSomfyAddress();
      case "somfy-fill":
        this.fillSomfy(true);
        this.dirty();
        return this.render();
      case "somfy-btn": return this.setSomfyButton(role, el.value);
      case "somfy-detect": return this.openSomfyDetect();
      case "follow-somfy": return this.addFollowSomfy(el.dataset.address);
      case "unfollow-somfy": {
        const d = this._state.draft;
        d.follow_somfy = (d.follow_somfy || []).filter((a) => String(a) !== el.dataset.address);
        this.dirty();
        return this.render();
      }
      case "follow":
        this._state.draft.follow = el.checked;
        this.dirty();
        return this.render();
      case "mirror":
        this._state.draft.mirror = el.checked;
        this.dirty();
        return this.render();
      case "linked":
      case "linked-light": {
        const d = this._state.draft;
        d[action === "linked" ? "linked_entity" : "linked_light_entity"] = el.value || null;
        if (action === "linked" && el.value && !Object.values(d.commands).some(hasCode)) this.fillLinked();
        this.dirty();
        return this.render();
      }
      case "linked-fill":
        this.fillLinked();
        this.dirty();
        return this.render();
      case "edit-action": return this.openAction(role);
      case "action-test": {
        const cmd = this.readAction();
        if (cmd) this.sendCommand(cmd);
        return;
      }
      case "action-save": return this.saveAction();
      case "add-extra": return this.addExtra();
      case "more": {
        const v = el.value;
        el.value = "";
        if (v === "paste") {
          this._state.dialog = { kind: "paste", role, result: null };
          this.render();
        } else if (v === "broadlink") this.openBroadlink(role);
        else if (v === "action") this.openAction(role);
        else if (v === "somfy") this.setSomfyButton(role, SOMFY_DEFAULT[role] || "my");
        else if (v === "device") this.openDevices(role);
        else if (v === "copy") this.showCode(role);
        else if (v === "clean") this.cleanRole(role);
        else if (v === "remove") {
          delete this._state.draft.commands[role];
          this.dirty();
          this.render();
        }
        return;
      }
      case "start-learn": return this.startLearn();
      case "close": return this.closeDialog();
      case "overlay":
        if (e.target === el) this.closeDialog();
        return;
      case "analyze": return this.analyzePasted();
      case "bl-use": return this.useBroadlink(el.dataset.code);
      case "relay-apply": return this.applyRelay();
      case "pct-reset":
        this._state.draft.options.speed_percentages = [];
        this.dirty();
        return this.render();
      case "calibrate": return this.openCalibration();
      case "calibrate-light": return this.openCalibration(true);
      case "cal-start": return this.startCalibration();
      case "cal-save": {
        const o = this._state.draft.options;
        if (!dlg.lightOnly) o.calibration = dlg.result;
        else if (o.calibration) {
          // A full table exists: refresh its lamp values and the "with light" column.
          const lamp = dlg.result.light - dlg.result.idle;
          o.calibration = { ...o.calibration, idle: dlg.result.idle, light: dlg.result.light, light_modes: dlg.result.light_modes,
            speeds: o.calibration.speeds.map(([off]) => [off, Math.round((off + lamp) * 10) / 10]) };
        } else o.light_calibration = dlg.result;
        this._state.dialog = null;
        return this.saveDraft();
      }
      case "cal-light-remove":
        this._state.draft.options.light_calibration = null;
        return this.render();
      case "cal-remove":
        this._state.draft.options.calibration = null;
        return this.render();
      case "copy-again": {
        const ta = this.shadowRoot.getElementById("code-view");
        ta.select();
        navigator.clipboard?.writeText(ta.value).then(() => this.toast(this.t("copied")), () => document.execCommand?.("copy"));
        return;
      }
      case "test-code": return this.send(el.dataset.which === "raw" ? dlg.result.raw : dlg.result.code, dlg.tx);
      case "use": return this.setCommand(dlg.role, dlg.result, el.dataset.which === "raw");
    }
  }
}

const STYLE = `
:host { display:block; min-height:100vh; background:var(--primary-background-color); color:var(--primary-text-color);
  font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
header { display:flex; align-items:center; gap:12px; height:56px; padding:0 16px; background:var(--app-header-background-color, var(--primary-color));
  color:var(--app-header-text-color, var(--text-primary-color)); position:sticky; top:0; z-index:2; }
header h1 { font-size:20px; font-weight:400; margin:0; }
header .ver { opacity:.7; font-size:12px; }
.menu { color:inherit; }
main { max-width:1100px; margin:0 auto; padding:16px; box-sizing:border-box; }
button, select, input, textarea { font:inherit; color:var(--primary-text-color); }
button { background:var(--card-background-color); border:1px solid var(--divider-color); border-radius:18px; padding:6px 14px; cursor:pointer; }
button:hover { border-color:var(--primary-color); }
button.primary { background:var(--primary-color); color:var(--text-primary-color); border-color:var(--primary-color); }
button.danger { color:var(--error-color); }
.icon-btn { background:none; border:none; font-size:20px; padding:4px 8px; border-radius:50%; }
select, input, textarea { background:var(--card-background-color); border:1px solid var(--divider-color); border-radius:8px; padding:8px; box-sizing:border-box; }
textarea { width:100%; font-family:monospace; font-size:12px; }
.toolbar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-bottom:16px; }
.spacer { flex:1; }
.grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(300px, 1fr)); gap:16px; }
.card, section { background:var(--card-background-color); border-radius:var(--ha-card-border-radius, 12px);
  box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); padding:16px; }
section { margin-bottom:16px; }
section h2, .dialog h2 { font-size:17px; font-weight:500; margin:0 0 12px; }
.card-head { display:flex; gap:12px; align-items:center; }
.icon { font-size:28px; }
.name { font-size:16px; font-weight:500; }
.sub { color:var(--secondary-text-color); font-size:13px; }
.mono { font-family:monospace; word-break:break-all; }
.chips { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin:12px 0; }
.chip { font-size:12px; padding:2px 8px; border-radius:10px; border:1px solid var(--divider-color); }
.chip.ok { background:rgba(67,160,71,.15); border-color:rgba(67,160,71,.5); }
.chip.warn { background:rgba(255,152,0,.18); border-color:rgba(255,152,0,.6); }
.chip.missing { background:rgba(219,68,55,.12); border-color:rgba(219,68,55,.5); }
.chip.opt { opacity:.6; }
.actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; align-items:center; }
.empty { text-align:center; padding:48px 16px; color:var(--secondary-text-color); }
.form { display:grid; grid-template-columns:repeat(auto-fill, minmax(240px, 1fr)); gap:12px 16px; }
.form label { display:flex; flex-direction:column; gap:4px; font-size:13px; color:var(--secondary-text-color); }
.form label > select, .form label > input { color:var(--primary-text-color); }
.form small, small.full { font-size:12px; grid-column:1/-1; color:var(--secondary-text-color); }
.slot { display:flex; gap:12px; align-items:center; flex-wrap:wrap; padding:12px 0; border-top:1px solid var(--divider-color); }
.slot:first-of-type { border-top:none; }
.slot-main { flex:1 1 220px; min-width:0; }
.slot-name { font-weight:500; }
.slot.todo .slot-name::before { content:"● "; color:var(--error-color); }
.slot.done .slot-name::before { content:"● "; color:var(--success-color, #43a047); }
.slot.opt .slot-name::before { content:"○ "; color:var(--secondary-text-color); }
.slot-actions { display:flex; gap:6px; align-items:center; }
.slot-actions select { border-radius:18px; padding:6px 10px; }
.warn-text { color:var(--warning-color, #ff9800); font-size:13px; margin-top:4px; }
.wave { width:240px; max-width:100%; }
.wave svg { width:100%; height:26px; display:block; }
.wave path { fill:none; stroke:var(--primary-color); stroke-width:1.4; vector-effect:non-scaling-stroke; }
.blocks { display:flex; gap:2px; margin-top:3px; }
.blk { flex:1; height:5px; border-radius:2px; max-width:18px; }
.blk.ok { background:var(--success-color, #43a047); } .blk.bad { background:var(--error-color, #db4437); }
.calblock { grid-column:1/-1; }
.form.ctl { margin-top:20px; padding-top:12px; border-top:1px solid var(--divider-color); }
.form.ctl h3 { margin:0; font-size:16px; font-weight:500; color:var(--primary-text-color); }
.form .actions.full { grid-column:1/-1; }
.edit-head { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
.edit-title { font-size:20px; font-weight:500; display:flex; align-items:center; gap:8px; }
.save-status { font-size:13px; padding:4px 10px; border-radius:12px; color:var(--secondary-text-color); }
.save-status.saved::before { content:"✓ "; color:var(--success-color, #43a047); }
.save-status.dirty, .save-status.saving { color:var(--warning-color, #ff9800); }
.save-status.error { color:var(--error-color); }
.tabs { display:flex; gap:4px; flex-wrap:wrap; border-bottom:1px solid var(--divider-color); margin-bottom:16px; }
.tab { border:none; border-bottom:3px solid transparent; border-radius:0; background:none; padding:10px 14px; color:var(--secondary-text-color); }
.tab.on { color:var(--primary-color); border-bottom-color:var(--primary-color); font-weight:500; }
.edit-grid { display:grid; grid-template-columns:minmax(0,1fr) 330px; gap:16px; align-items:start; }
.live { position:sticky; top:72px; background:var(--card-background-color); border-radius:var(--ha-card-border-radius,12px);
  box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); padding:14px; max-height:calc(100vh - 90px); overflow:auto; }
.live h2 { font-size:16px; margin:0 0 8px; }
.live h3, .live-inline h3 { font-size:13px; text-transform:uppercase; letter-spacing:.04em; color:var(--secondary-text-color); margin:12px 0 6px; }
.lcard { border:1px solid var(--divider-color); border-radius:10px; padding:10px; margin-bottom:8px; }
.chip-group { align-self:center; }
.devlinks { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:10px; }
.devlinks b { width:100%; font-size:.9em; }
.devlinks small { width:100%; color:var(--secondary-text-color); }
button.link { background:none; border:1px solid var(--divider-color); color:var(--primary-color); border-radius:16px; padding:4px 10px; cursor:pointer; }
.lhead { display:flex; align-items:center; gap:10px; }
.licon { font-size:20px; }
.lname { flex:1; font-size:14px; font-weight:500; min-width:0; }
.lrow { display:flex; flex-direction:column; font-size:12px; color:var(--secondary-text-color); margin-top:8px; }
.lrow input[type=range] { width:100%; }
.chipbtn { padding:4px 10px; font-size:13px; }
.measure { border:1px solid var(--divider-color); border-radius:8px; padding:12px; }
.measure .clock { font-size:28px; font-variant-numeric:tabular-nums; margin-left:12px; }
.chipbtn.sync { border-style:dashed; }
.badge { font-size:11px; color:var(--success-color, #43a047); white-space:nowrap; }
.synccheck { font-size:12px; margin:8px 0 0; color:var(--secondary-text-color); }
.chipbtn.on { background:var(--primary-color); color:var(--text-primary-color); border-color:var(--primary-color); }
.lcard .chips { margin:8px 0 0; }
.tgl { width:44px; height:24px; border-radius:12px; padding:0; position:relative; background:var(--divider-color); border:none; }
.tgl span { position:absolute; top:3px; left:3px; width:18px; height:18px; border-radius:50%; background:#fff; transition:left .15s; }
.tgl.on { background:var(--primary-color); }
.tgl.on span { left:23px; }
.tab-live { display:none; }
@media (max-width:1000px) {
  .edit-grid { grid-template-columns:1fr; }
  .live { display:none; }
  .tab-live { display:inline-block; }
  .tabs { flex-wrap:nowrap; overflow-x:auto; scrollbar-width:none; }
  .tab { white-space:nowrap; padding:10px; }
  .edit-title { font-size:17px; }
}
section h3 { font-size:14px; font-weight:500; margin:12px 0 0; }
.form .full { grid-column:1/-1; }
.diagram { width:100%; max-width:620px; display:block; margin:8px auto 12px; }
.dg-box { fill:var(--secondary-background-color, rgba(127,127,127,.1)); stroke:var(--divider-color); }
.dg-t { font-size:13px; fill:var(--primary-text-color); text-anchor:middle; font-weight:500; }
.dg-s { font-size:11px; fill:var(--secondary-text-color); text-anchor:middle; }
.dg-power { stroke:#f5a623; stroke-width:3; fill:none; }
.dg-data { stroke:var(--primary-color); stroke-width:2; stroke-dasharray:5 4; fill:none; }
.dg-rf { stroke:#9c6ade; stroke-width:2; stroke-dasharray:2 4; fill:none; }
.dg-cut { stroke:var(--divider-color); stroke-width:2; stroke-dasharray:3 5; }
.dg-x { fill:var(--error-color, #db4437); font-size:14px; text-anchor:middle; }
.dg-ar { fill:var(--secondary-text-color); }
table.cal { border-collapse:collapse; font-size:13px; margin:6px 0; }
.calcell { width:70px; padding:3px 6px; }
input.dec { font-variant-numeric:tabular-nums; }
.timeline { background:var(--secondary-background-color, rgba(127,127,127,.08)); border-radius:10px; padding:10px 12px; font-size:13px; }
.tl { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin-top:6px; }
.tl-step { background:var(--card-background-color); border:1px solid var(--divider-color); border-radius:8px; padding:4px 8px; }
.tl-wait { color:var(--primary-color); font-weight:500; }
.tl-wait::before { content:"→ "; } .tl-wait::after { content:" →"; }
table.cal td, table.cal th { padding:3px 12px 3px 0; text-align:left; border-bottom:1px solid var(--divider-color); }
.cal-lines { font-size:14px; display:flex; flex-direction:column; gap:3px; }
.lives { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 4px; }
.lives:empty { display:none; }
.live { font-size:12px; padding:3px 9px; border-radius:10px; background:var(--secondary-background-color, rgba(127,127,127,.12)); }
.live.on { background:rgba(255,193,7,.22); }
.live.off { opacity:.75; }
.frames { display:flex; gap:4px; align-items:center; font-size:12px; color:var(--secondary-text-color); }
.frames select { padding:4px 6px; border-radius:12px; }
.hold { display:flex; gap:6px; align-items:center; font-size:12px; color:var(--secondary-text-color); margin-top:4px; }
.hold input { width:70px; padding:4px 6px; }
label.check.full { flex-direction:row; grid-column:1/-1; align-items:center; }
.add-extra { display:flex; gap:8px; margin-top:12px; padding-top:12px; border-top:1px solid var(--divider-color); }
.add-extra input { flex:1; }
.overlay { position:fixed; inset:0; background:rgba(0,0,0,.45); display:flex; align-items:center; justify-content:center; z-index:10; padding:16px; }
.dialog { background:var(--card-background-color); border-radius:16px; padding:20px; width:min(560px, 100%); max-height:90vh; overflow:auto; box-sizing:border-box; }
.dialog-head { display:flex; justify-content:space-between; align-items:flex-start; }
.stage { display:flex; gap:16px; align-items:center; padding:12px 0; font-size:16px; }
.pulse { width:22px; height:22px; flex:none; border-radius:50%; background:var(--primary-color); animation:p 1.2s infinite ease-in-out; }
@keyframes p { 0%,100% { transform:scale(.6); opacity:.5 } 50% { transform:scale(1); opacity:1 } }
.res { padding:10px 0; border-top:1px solid var(--divider-color); }
.res .wave { width:100%; margin-top:6px; }
.check { display:flex; gap:8px; align-items:center; margin:8px 0; }
.bl-row { display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-top:1px solid var(--divider-color); gap:8px; }
.toast { position:fixed; bottom:24px; left:50%; transform:translateX(-50%); background:#323232; color:#fff; padding:10px 18px; border-radius:8px; z-index:20; }
.toast.err { background:var(--error-color, #db4437); }
@media (max-width:600px) { .wave { width:100%; } main { padding:12px; } }
`;

// A newer version loaded over an open page must not throw; a reload picks it up.
if (!customElements.get("rf-devices-panel")) customElements.define("rf-devices-panel", RFDevicesPanel);
