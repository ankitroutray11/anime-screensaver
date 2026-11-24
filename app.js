/**
 * KURO // ANIME — Dark Anime Screensaver Engine
 * Transactional Wallpaper Lifecycle: UNSEEN -> RESERVED -> DISPLAYED
 * Guarantees zero duplicates, persistent SQLite tracking across restarts,
 * session backward/forward navigation, and graceful collection exhaustion.
 */

(function () {
  'use strict';

  // --- CONFIGURATION & STATE ---
  const STATE = {
    displayMode: localStorage.getItem('kuro_display_mode') || 'ambient', // 'ambient' | 'cinematic' | 'dashboard'
    currentAnime: localStorage.getItem('kuro_anime') || 'all',
    currentCharacter: localStorage.getItem('kuro_character') || 'all',
    aspectRatio: localStorage.getItem('kuro_ratio') || 'auto', // 'auto' | 'landscape' | 'ultrawide' | 'portrait' | 'any'
    targetMonitor: localStorage.getItem('kuro_target_monitor') || 'auto',
    focalPointMode: localStorage.getItem('kuro_focal_point') || 'auto',
    connectedMonitors: [],
    currentTopology: { orientation: 'landscape', width: 0, height: 0, dpr: 1 },
    wasMonitorDisconnected: false,
    intervalSeconds: parseInt(localStorage.getItem('kuro_interval') || '30', 10),
    transitionStyle: localStorage.getItem('kuro_transition') || 'random',
    transitionDuration: parseFloat(localStorage.getItem('kuro_transition_duration') || '2.5'),
    motionStyle: localStorage.getItem('kuro_motion') || 'random',
    reducedMotion: localStorage.getItem('kuro_reduced_motion') === 'true',
    timeFormat: localStorage.getItem('kuro_timeformat') || '12',
    showSeconds: localStorage.getItem('kuro_show_seconds') !== 'false',
    dateFormat: localStorage.getItem('kuro_date_format') || 'full', // 'full' | 'standard' | 'iso' | 'anime_jp'
    secondTimeZone: localStorage.getItem('kuro_second_tz') || 'none',
    tempUnit: localStorage.getItem('kuro_temp_unit') || 'C', // 'C' or 'F'
    particlesEnabled: localStorage.getItem('kuro_particles') !== 'false',
    customCity: localStorage.getItem('kuro_city') || '',
    detectedCityName: '',
    // OLED Care & Burn-in Reduction
    oledEnabled: localStorage.getItem('kuro_oled_enabled') !== 'false',
    oledAutoDim: localStorage.getItem('kuro_oled_auto_dim') !== 'false',
    oledIdleOpacity: parseInt(localStorage.getItem('kuro_oled_idle_opacity') || '15', 10),
    hudBaseOpacity: parseInt(localStorage.getItem('kuro_hud_base_opacity') || '100', 10),
    oledHudShift: localStorage.getItem('kuro_oled_hud_shift') !== 'false',
    oledWpShift: localStorage.getItem('kuro_oled_wp_shift') !== 'false',
    oledSoftWhite: localStorage.getItem('kuro_oled_soft_white') !== 'false',
    oledScrim: parseInt(localStorage.getItem('kuro_oled_scrim') || '0', 10),
    oledNightMode: localStorage.getItem('kuro_oled_night_mode') || 'off', // 'off' | 'auto' | 'always'
    isPaused: false,
    hudVisible: true,
    activeLayer: 'a', // 'a' or 'b'
    currentWallpaper: null,
    sessionHistory: [],
    sessionHistoryIndex: -1,
    favorites: JSON.parse(localStorage.getItem('kuro_favorites') || '[]'),
    isTransitioning: false,
    timer: null,
    progressRaf: null,
    slideStartTime: null,
    idleTimer: null,
    cinematicRevealTimer: null,
    extractedAccent: null,
    backendBase: '',
    franchisesList: [],
    // Artwork Information & Composition State
    currentSessionSequence: 0,
    artworkInfoModalOpen: false,
    compositionModalOpen: false,
    compositionSettings: {
      default_mode_landscape: 'fill',
      default_mode_portrait: 'fit',
      default_mode_ultrawide: 'fill',
      blurred_backdrop_enabled: true,
      blur_intensity_px: 28,
      backdrop_opacity: 0.65,
      auto_focal_protection: true
    },
    currentComposition: null,
    editingFocalPoint: { x: 50.0, y: 50.0 },
    editingDisplayMode: 'fill',
    editingBlurredBackdrop: true,
    editingCharacters: [],
    lastMotionIndex: -1,
    lastTransitionIndex: -1,
    sessionToken: null,
    // Performance Monitoring & Adaptive Rendering State
    diagnosticsOpen: false,
    diagnosticsPollTimer: null,
    currentFps: 60,
    fpsHistory: [],
    lastImageLoadMs: 0,
    lastImageDecodeMs: 0,
    lastImageTotalMs: 0,
    qualityProfile: localStorage.getItem('kuro_quality_profile') || 'auto',
    effectiveQualityProfile: 'high',
    // Offline-first fallback tracking
    isOffline: !navigator.onLine,
    activeLevel: 1,
    cachedCount: 0,
    curatedCount: 0,
    // Intelligent Recommendations & Personalization
    currentWallpaperStartTime: null,
    wasExplicitlySkipped: false,
    // Intelligent Slideshow Scheduling
    schedulerStrategy: localStorage.getItem('kuro_scheduler_strategy') || 'fixed',
    schedulerFixedSec: parseInt(localStorage.getItem('kuro_scheduler_fixed_sec') || '30', 10),
    schedulerRandMin: parseInt(localStorage.getItem('kuro_scheduler_rand_min') || '15', 10),
    schedulerRandMax: parseInt(localStorage.getItem('kuro_scheduler_rand_max') || '60', 10),
    schedulerDaySec: parseInt(localStorage.getItem('kuro_scheduler_day_sec') || '25', 10),
    schedulerEveSec: parseInt(localStorage.getItem('kuro_scheduler_eve_sec') || '35', 10),
    schedulerNightSec: parseInt(localStorage.getItem('kuro_scheduler_night_sec') || '60', 10),
    schedulerCinematicSec: parseInt(localStorage.getItem('kuro_scheduler_cinematic_sec') || '45', 10),
    schedulerDashboardSec: parseInt(localStorage.getItem('kuro_scheduler_dashboard_sec') || '20', 10),
    schedulerQualityBonus: localStorage.getItem('kuro_scheduler_quality_bonus') !== 'false',
    pauseOnHidden: localStorage.getItem('kuro_scheduler_pause_hidden') !== 'false',
    isPausedForHidden: false,
    savedElapsed: 0,
    currentSlideDuration: 30000,
    franchiseRotationInterval: parseInt(localStorage.getItem('kuro_scheduler_franchise_rot_interval') || '5', 10),
    franchiseSlideCount: 0,
    currentFranchiseRotIdx: 0,
    // Ambient Soundscape System (Optional & Starts Muted)
    soundscapeEnabled: localStorage.getItem('kuro_soundscape_enabled') === 'true',
    soundscapeTrack: localStorage.getItem('kuro_soundscape_track') || 'rain',
    soundscapeVolume: parseInt(localStorage.getItem('kuro_soundscape_volume') || '40', 10),
    soundscapeMuted: localStorage.getItem('kuro_soundscape_muted') !== 'false',
    soundscapeCrossfade: parseFloat(localStorage.getItem('kuro_soundscape_crossfade') || '2.5'),
    soundscapeCatalog: [],
    audioChannelA: null,
    audioChannelB: null,
    activeAudioChannel: 'a',
    soundscapeCrossfadeTimer: null,
    // Visual Wallpaper History Explorer State
    historyOpen: false,
    historyPage: 1,
    historyPageSize: 24,
    historyFranchise: 'all',
    historyDateFilter: 'all',
    historyResolution: 'all',
    historyFavsOnly: false,
    historySortBy: 'newest',
    historySearchQuery: '',
    historyTotalPages: 1,
    historyTotalCount: 0
  };

  // DOM Elements
  const DOM = {
    layerA: document.getElementById('bg-layer-a'),
    layerB: document.getElementById('bg-layer-b'),
    bufferIndicator: document.getElementById('buffer-indicator'),
    statsBadge: document.getElementById('stats-badge'),
    networkPill: document.getElementById('network-pill'),
    metaOfflineBadge: document.getElementById('meta-offline-badge'),
    clockHoursMins: document.getElementById('clock-hours-mins'),
    clockSeconds: document.getElementById('clock-seconds'),
    clockAmPm: document.getElementById('clock-ampm'),
    clockDateText: document.getElementById('clock-date-text'),
    clockSecondTzRow: document.getElementById('clock-second-tz-row'),
    clockSecondTzLabel: document.getElementById('clock-second-tz-label'),
    clockSecondTzTime: document.getElementById('clock-second-tz-time'),
    weatherTemp: document.getElementById('weather-temp'),
    weatherDesc: document.getElementById('weather-desc'),
    weatherIcon: document.getElementById('weather-icon'),
    weatherCity: document.getElementById('weather-city'),
    weatherFeels: document.getElementById('weather-feels'),
    weatherHumidity: document.getElementById('weather-humidity'),
    weatherWind: document.getElementById('weather-wind'),
    weatherSun: document.getElementById('weather-sun'),
    btnPrev: document.getElementById('btn-prev'),
    btnPlayPause: document.getElementById('btn-play-pause'),
    btnNext: document.getElementById('btn-next'),
    iconPause: document.getElementById('icon-pause'),
    iconPlay: document.getElementById('icon-play'),
    slideProgress: document.getElementById('slide-progress'),
    progressTimerText: document.getElementById('progress-timer-text'),
    hudBottomLeft: document.getElementById('hud-bottom-left'),
    tagRes: document.getElementById('tag-res'),
    tagMood: document.getElementById('tag-mood'),
    tagCharacter: document.getElementById('tag-character'),
    tagPalette: document.getElementById('tag-palette'),
    btnFavorite: document.getElementById('btn-favorite'),
    favLabel: document.getElementById('fav-label'),
    btnDownload: document.getElementById('btn-download'),
    ambientCanvas: document.getElementById('ambient-canvas'),
    modePills: document.querySelectorAll('.mode-pill'),
    dashStatSeen: document.getElementById('dash-stat-seen'),
    dashStatFavs: document.getElementById('dash-stat-favs'),
    dashStatRatio: document.getElementById('dash-stat-ratio'),
    settingsModal: document.getElementById('settings-modal'),
    btnSettingsOpen: document.getElementById('btn-settings-open'),
    btnSettingsClose: document.getElementById('btn-settings-close'),
    btnFullscreen: document.getElementById('btn-fullscreen'),
    btnToggleHud: document.getElementById('btn-toggle-hud'),
    btnToggleParticles: document.getElementById('btn-toggle-particles'),
    btnToggleDiagnostics: document.getElementById('btn-toggle-diagnostics'),
    perfDiagnosticsOverlay: document.getElementById('perf-diagnostics-overlay'),
    perfProfilePill: document.getElementById('perf-profile-pill'),
    btnPerfResetMetrics: document.getElementById('btn-perf-reset-metrics'),
    btnPerfClose: document.getElementById('btn-perf-close'),
    perfProfileSelector: document.getElementById('perf-profile-selector'),
    perfProfileButtons: document.querySelectorAll('.perf-pill-btn'),
    perfValFps: document.getElementById('perf-val-fps'),
    perfSubFps: document.getElementById('perf-sub-fps'),
    perfFpsDot: document.getElementById('perf-fps-dot'),
    perfValMem: document.getElementById('perf-val-mem'),
    perfUnitMem: document.getElementById('perf-unit-mem'),
    perfSubMem: document.getElementById('perf-sub-mem'),
    perfMemDot: document.getElementById('perf-mem-dot'),
    perfValImgTime: document.getElementById('perf-val-img-time'),
    perfSubImgTime: document.getElementById('perf-sub-img-time'),
    perfImgDot: document.getElementById('perf-img-dot'),
    perfValQueue: document.getElementById('perf-val-queue'),
    perfSubQueue: document.getElementById('perf-sub-queue'),
    perfQueueDot: document.getElementById('perf-queue-dot'),
    perfValCacheRate: document.getElementById('perf-val-cache-rate'),
    perfSubCache: document.getElementById('perf-sub-cache'),
    perfCacheDot: document.getElementById('perf-cache-dot'),
    perfValRespTime: document.getElementById('perf-val-resp-time'),
    perfSubResp: document.getElementById('perf-sub-resp'),
    perfRespDot: document.getElementById('perf-resp-dot'),
    perfValSqlTime: document.getElementById('perf-val-sql-time'),
    perfSubSql: document.getElementById('perf-sub-sql'),
    perfSqlDot: document.getElementById('perf-sql-dot'),
    perfValFailRate: document.getElementById('perf-val-fail-rate'),
    perfSubFail: document.getElementById('perf-sub-fail'),
    perfApiDot: document.getElementById('perf-api-dot'),
    perfValWorkers: document.getElementById('perf-val-workers'),
    perfSubWorkers: document.getElementById('perf-sub-workers'),
    perfWorkerDot: document.getElementById('perf-worker-dot'),
    // Multi-Provider Failover & Health elements
    providerToggleWallhaven: document.getElementById('provider-toggle-wallhaven'),
    providerToggleSafebooru: document.getElementById('provider-toggle-safebooru'),
    providerToggleKonachan: document.getElementById('provider-toggle-konachan'),
    providerBadgeWallhaven: document.getElementById('provider-badge-wallhaven'),
    providerBadgeSafebooru: document.getElementById('provider-badge-safebooru'),
    providerBadgeKonachan: document.getElementById('provider-badge-konachan'),
    providerDiagActive: document.getElementById('provider-diag-active'),
    providerDiagFailovers: document.getElementById('provider-diag-failovers'),
    btnProviderResetCircuits: document.getElementById('btn-provider-reset-circuits'),
    perfValProvider: document.getElementById('perf-val-provider'),
    perfSubProvider: document.getElementById('perf-sub-provider'),
    perfProviderDot: document.getElementById('perf-provider-dot'),
    // Tag Intelligence elements
    inputVerifyTagId: document.getElementById('input-verify-tag-id'),
    btnVerifyTagId: document.getElementById('btn-verify-tag-id'),
    tagVerifyResult: document.getElementById('tag-verify-result'),
    btnTagCatalogRefresh: document.getElementById('btn-tag-catalog-refresh'),
    btnTagCatalogReset: document.getElementById('btn-tag-catalog-reset'),
    tagCatalogCount: document.getElementById('tag-catalog-count'),
    tagCatalogTbody: document.getElementById('tag-catalog-tbody'),
    toast: document.getElementById('toast'),
    quickMoods: document.querySelectorAll('.mood-btn'),
    settingAnime: document.getElementById('setting-anime'),
    settingCharacter: document.getElementById('setting-character'),
    groupCharacter: document.getElementById('group-character'),
    // Setting inputs
    settingDisplayMode: document.getElementById('setting-display-mode'),
    settingInterval: document.getElementById('setting-interval'),
    settingIntervalLabel: document.getElementById('setting-interval-label'),
    // Intelligent Scheduling elements
    settingScheduleStrategy: document.getElementById('setting-schedule-strategy'),
    panelFixedInterval: document.getElementById('panel-fixed-interval'),
    panelRandomInterval: document.getElementById('panel-random-interval'),
    panelTimeSlots: document.getElementById('panel-time-slots'),
    panelFranchiseRotation: document.getElementById('panel-franchise-rotation'),
    settingRandomMin: document.getElementById('setting-random-min'),
    settingRandomMinLabel: document.getElementById('setting-random-min-label'),
    settingRandomMax: document.getElementById('setting-random-max'),
    settingRandomMaxLabel: document.getElementById('setting-random-max-label'),
    settingDaySec: document.getElementById('setting-day-sec'),
    settingEveSec: document.getElementById('setting-eve-sec'),
    settingNightSec: document.getElementById('setting-night-sec'),
    settingFranchiseRotInterval: document.getElementById('setting-franchise-rot-interval'),
    settingFranchiseRotLabel: document.getElementById('setting-franchise-rot-label'),
    settingCinematicSec: document.getElementById('setting-cinematic-sec'),
    settingCinematicSecLabel: document.getElementById('setting-cinematic-sec-label'),
    settingDashboardSec: document.getElementById('setting-dashboard-sec'),
    settingDashboardSecLabel: document.getElementById('setting-dashboard-sec-label'),
    settingScheduleQualityBonus: document.getElementById('setting-schedule-quality-bonus'),
    settingSchedulePauseHidden: document.getElementById('setting-schedule-pause-hidden'),
    // Ambient Soundscape elements
    btnSoundscapeToggle: document.getElementById('btn-soundscape-toggle'),
    settingSoundscapeEnabled: document.getElementById('setting-soundscape-enabled'),
    soundscapeSubcontrols: document.getElementById('soundscape-subcontrols'),
    settingSoundscapeTrack: document.getElementById('setting-soundscape-track'),
    btnSoundscapeMute: document.getElementById('btn-soundscape-mute'),
    settingSoundscapeVolume: document.getElementById('setting-soundscape-volume'),
    settingSoundscapeVolLabel: document.getElementById('setting-soundscape-vol-label'),
    settingSoundscapeCrossfade: document.getElementById('setting-soundscape-crossfade'),
    settingSoundscapeFadeLabel: document.getElementById('setting-soundscape-fade-label'),
    settingTransition: document.getElementById('setting-transition'),
    settingTransitionDuration: document.getElementById('setting-transition-duration'),
    settingMotion: document.getElementById('setting-motion'),
    settingReducedMotion: document.getElementById('setting-reduced-motion'),
    settingMonitor: document.getElementById('setting-monitor'),
    settingRatio: document.getElementById('setting-ratio'),
    settingFocalPoint: document.getElementById('setting-focal-point'),
    settingShowSeconds: document.getElementById('setting-show-seconds'),
    settingDateFormat: document.getElementById('setting-date-format'),
    settingSecondTz: document.getElementById('setting-second-tz'),
    settingParticles: document.getElementById('setting-particles'),
    settingCity: document.getElementById('setting-city'),
    btnSaveCity: document.getElementById('btn-save-city'),
    btnAutoCity: document.getElementById('btn-auto-city'),
    statWeatherLocation: document.getElementById('stat-weather-location'),
    // OLED Protection elements
    oledDarkeningOverlay: document.getElementById('oled-darkening-overlay'),
    settingOledEnabled: document.getElementById('setting-oled-enabled'),
    oledSubcontrols: document.getElementById('oled-subcontrols'),
    settingOledAutoDim: document.getElementById('setting-oled-auto-dim'),
    settingOledIdleOpacity: document.getElementById('setting-oled-idle-opacity'),
    settingOledIdleOpacityLabel: document.getElementById('setting-oled-idle-opacity-label'),
    settingHudBaseOpacity: document.getElementById('setting-hud-base-opacity'),
    settingHudBaseOpacityLabel: document.getElementById('setting-hud-base-opacity-label'),
    settingOledHudShift: document.getElementById('setting-oled-hud-shift'),
    settingOledWpShift: document.getElementById('setting-oled-wp-shift'),
    settingOledSoftWhite: document.getElementById('setting-oled-soft-white'),
    settingOledScrim: document.getElementById('setting-oled-scrim'),
    settingOledScrimLabel: document.getElementById('setting-oled-scrim-label'),
    settingOledNightMode: document.getElementById('setting-oled-night-mode'),
    statViewportRes: document.getElementById('stat-viewport-res'),
    statDpiScale: document.getElementById('stat-dpi-scale'),
    statActiveMonitor: document.getElementById('stat-active-monitor'),
    statTotalSeen: document.getElementById('stat-total-seen'),
    statFavoritesCount: document.getElementById('stat-favorites-count'),
    btnClearHistory: document.getElementById('btn-clear-history'),
    // Advanced Control Center elements
    settingsSearchInput: document.getElementById('settings-search-input'),
    btnSettingsSearchClear: document.getElementById('btn-settings-search-clear'),
    controlCenterNav: document.querySelector('.control-center-nav'),
    navTabs: document.querySelectorAll('.nav-tab'),
    controlSections: document.querySelectorAll('.control-center-section'),
    activeSectionTitle: document.getElementById('active-section-title'),
    activeSectionDesc: document.getElementById('active-section-desc'),
    btnResetSection: document.getElementById('btn-reset-section'),
    settingsValidationBadge: document.getElementById('settings-validation-badge'),
    settingsChangesBadge: document.getElementById('settings-changes-badge'),
    btnSettingsCancel: document.getElementById('btn-settings-cancel'),
    btnSettingsSave: document.getElementById('btn-settings-save'),
    settingVisualTheme: document.getElementById('setting-visual-theme'),
    settingVisualDynamicAccent: document.getElementById('setting-visual-dynamic-accent'),
    settingVisualAccentColor: document.getElementById('setting-visual-accent-color'),
    settingMotionIntensity: document.getElementById('setting-motion-intensity'),
    settingParticleDensity: document.getElementById('setting-particle-density'),
    settingParticleSpeed: document.getElementById('setting-particle-speed'),
    settingDisplayOrientation: document.getElementById('setting-display-orientation'),
    settingWinScaling: document.getElementById('setting-win-scaling'),
    settingUiScale: document.getElementById('setting-ui-scale'),
    settingWpFitMode: document.getElementById('setting-wp-fit-mode'),
    settingCompBlurEnabled: document.getElementById('setting-comp-blur-enabled'),
    settingCompBlurIntensity: document.getElementById('setting-comp-blur-intensity'),
    settingCompBlurLabel: document.getElementById('setting-comp-blur-label'),
    settingMinResolution: document.getElementById('setting-min-resolution'),
    settingDuplicateSensitivity: document.getElementById('setting-duplicate-sensitivity'),
    settingPerfPrefetch: document.getElementById('setting-perf-prefetch'),
    settingPerfPrefetchLabel: document.getElementById('setting-perf-prefetch-label'),
    settingPerfCacheLimit: document.getElementById('setting-perf-cache-limit'),
    settingPerfCacheLimitLabel: document.getElementById('setting-perf-cache-limit-label'),
    settingPerfWorkers: document.getElementById('setting-perf-workers'),
    settingPerfDownloadLimit: document.getElementById('setting-perf-download-limit'),
    settingPerfAnimQuality: document.getElementById('setting-perf-anim-quality'),
    statCacheUtilization: document.getElementById('stat-cache-utilization'),
    btnExportSettings: document.getElementById('btn-export-settings'),
    btnImportSettings: document.getElementById('btn-import-settings'),
    inputImportSettings: document.getElementById('input-import-settings'),
    btnFactoryReset: document.getElementById('btn-factory-reset'),
    btnPurgeCache: document.getElementById('btn-purge-cache'),
    // Backup & Recovery & Database Integrity
    dbIntegrityBadge: document.getElementById('db-integrity-badge'),
    dbMetricSchema: document.getElementById('db-metric-schema'),
    dbMetricTables: document.getElementById('db-metric-tables'),
    dbMetricSize: document.getElementById('db-metric-size'),
    dbMetricWal: document.getElementById('db-metric-wal'),
    btnCheckIntegrity: document.getElementById('btn-check-integrity'),
    chkBackupFavorites: document.getElementById('chk-backup-favorites'),
    chkBackupCache: document.getElementById('chk-backup-cache'),
    inputBackupNote: document.getElementById('input-backup-note'),
    btnCreateBackup: document.getElementById('btn-create-backup'),
    btnUploadBackup: document.getElementById('btn-upload-backup'),
    inputUploadBackupFile: document.getElementById('input-upload-backup-file'),
    btnRefreshBackups: document.getElementById('btn-refresh-backups'),
    backupListContainer: document.getElementById('backup-list-container'),
    backupListEmpty: document.getElementById('backup-list-empty'),
    settingMaxAutoBackups: document.getElementById('setting-max-auto-backups'),
    backupRestoreModal: document.getElementById('backup-restore-modal'),
    restoreTargetName: document.getElementById('restore-target-name'),
    chkRestoreFavs: document.getElementById('chk-restore-favs'),
    chkRestoreCache: document.getElementById('chk-restore-cache'),
    btnRestoreCancel: document.getElementById('btn-restore-cancel'),
    btnRestoreConfirm: document.getElementById('btn-restore-confirm'),
    swatches: document.querySelectorAll('.color-swatch'),
    // Library & Collection Management
    btnLibraryOpen: document.getElementById('btn-library-open'),
    btnBlacklistCurrent: document.getElementById('btn-blacklist-current'),
    libraryModal: document.getElementById('library-modal'),
    btnLibraryClose: document.getElementById('btn-library-close'),
    libTabBtns: document.querySelectorAll('.library-tab-btn'),
    libTabPanels: document.querySelectorAll('.library-tab-panel'),
    libTabFavCount: document.getElementById('lib-tab-fav-count'),
    libTabColCount: document.getElementById('lib-tab-col-count'),
    libTabBlCount: document.getElementById('lib-tab-bl-count'),
    // Favorites Tab
    favSearchInput: document.getElementById('fav-search-input'),
    favSearchClear: document.getElementById('fav-search-clear'),
    favFilterFranchise: document.getElementById('fav-filter-franchise'),
    favFilterRes: document.getElementById('fav-filter-res'),
    btnRefreshFavorites: document.getElementById('btn-refresh-favorites'),
    favoritesGrid: document.getElementById('favorites-grid'),
    favoritesEmpty: document.getElementById('favorites-empty'),
    // Collections Tab
    btnNewCollection: document.getElementById('btn-new-collection'),
    collectionsList: document.getElementById('collections-list'),
    activeColName: document.getElementById('active-col-name'),
    activeColDesc: document.getElementById('active-col-desc'),
    btnRenameCol: document.getElementById('btn-rename-col'),
    btnDeleteCol: document.getElementById('btn-delete-col'),
    colSearchInput: document.getElementById('col-search-input'),
    colFilterFranchise: document.getElementById('col-filter-franchise'),
    colFilterRes: document.getElementById('col-filter-res'),
    collectionItemsGrid: document.getElementById('collection-items-grid'),
    collectionItemsEmpty: document.getElementById('collection-items-empty'),
    // Blacklist Tab
    blacklistGrid: document.getElementById('blacklist-grid'),
    blacklistEmpty: document.getElementById('blacklist-empty'),
    // Stats Tab
    statLibDisplayed: document.getElementById('stat-lib-displayed'),
    statLibFranchises: document.getElementById('stat-lib-franchises'),
    statLibFavorites: document.getElementById('stat-lib-favorites'),
    statLibBlacklisted: document.getElementById('stat-lib-blacklisted'),
    storageCachePercent: document.getElementById('storage-cache-percent'),
    storageCacheProgress: document.getElementById('storage-cache-progress'),
    storageFavoritesSize: document.getElementById('storage-favorites-size'),
    storageFavoritesFiles: document.getElementById('storage-favorites-files'),
    storageCacheSize: document.getElementById('storage-cache-size'),
    storageCacheFiles: document.getElementById('storage-cache-files'),
    storageTotalSize: document.getElementById('storage-total-size'),
    storageTotalGb: document.getElementById('storage-total-gb'),
    btnPurgeCache: document.getElementById('btn-purge-cache'),
    btnRefreshStorage: document.getElementById('btn-refresh-storage'),
    // Prompt Dialogs
    collectionPromptModal: document.getElementById('collection-prompt-modal'),
    promptModalTitle: document.getElementById('prompt-modal-title'),
    btnPromptClose: document.getElementById('btn-prompt-close'),
    promptInputName: document.getElementById('prompt-input-name'),
    promptInputDesc: document.getElementById('prompt-input-desc'),
    btnPromptConfirm: document.getElementById('btn-prompt-confirm'),
    btnPromptCancel: document.getElementById('btn-prompt-cancel'),
    // Add to Collection Picker Modal
    addToCollectionModal: document.getElementById('add-to-collection-modal'),
    btnAddColClose: document.getElementById('btn-add-col-close'),
    addColWpid: document.getElementById('add-col-wpid'),
    addColPickerList: document.getElementById('add-col-picker-list'),
    // Exhaustion Modal
    exhaustionOverlay: document.getElementById('exhaustion-overlay'),
    exhaustionTitle: document.getElementById('exhaustion-title'),
    exhaustionMsg: document.getElementById('exhaustion-msg'),
    btnExhaustionSwitch: document.getElementById('btn-exhaustion-switch'),
    btnExhaustionSettings: document.getElementById('btn-exhaustion-settings'),
    // Exit & Windows Launcher Config
    btnExitScreensaver: document.getElementById('btn-exit-screensaver'),
    btnSettingsExit: document.getElementById('btn-settings-exit'),
    settingWinStartup: document.getElementById('setting-win-startup'),
    settingLaunchMode: document.getElementById('setting-launch-mode'),
    // Personalization Controls
    settingRecEnabled: document.getElementById('setting-rec-enabled'),
    recSubcontrols: document.getElementById('rec-subcontrols'),
    settingRecDiversity: document.getElementById('setting-rec-diversity'),
    recEventsBadge: document.getElementById('rec-events-badge'),
    recFranchiseChips: document.getElementById('rec-franchise-chips'),
    recCharacterChips: document.getElementById('rec-character-chips'),
    recManualFranchiseSelect: document.getElementById('rec-manual-franchise-select'),
    recManualScoreInput: document.getElementById('rec-manual-score-input'),
    btnRecApplyBias: document.getElementById('btn-rec-apply-bias'),
    recStatDwell: document.getElementById('rec-stat-dwell'),
    recStatSkips: document.getElementById('rec-stat-skips'),
    recStatRevisits: document.getElementById('rec-stat-revisits'),
    btnRecReset: document.getElementById('btn-rec-reset'),
    // Quality Scoring Controls
    tagQuality: document.getElementById('tag-quality'),
    qualityAvgBadge: document.getElementById('quality-avg-badge'),
    settingQualityThreshold: document.getElementById('setting-quality-threshold'),
    settingQualityThresholdLabel: document.getElementById('setting-quality-threshold-label'),
    settingQualityNativeRes: document.getElementById('setting-quality-native-res'),
    settingQualityAspectRatio: document.getElementById('setting-quality-aspect-ratio'),
    settingQualityAvoidBright: document.getElementById('setting-quality-avoid-bright'),
    settingQualityAvoidDark: document.getElementById('setting-quality-avoid-dark'),
    settingQualityPopWeight: document.getElementById('setting-quality-pop-weight'),
    btnQualityRescore: document.getElementById('btn-quality-rescore'),
    // Artwork Information Panel Elements
    modalArtworkInfo: document.getElementById('modal-artwork-info'),
    btnArtinfoClose: document.getElementById('btn-artinfo-close'),
    btnQuickInfo: document.getElementById('btn-quick-info'),
    btnInfo: document.getElementById('btn-info'),
    artinfoTitle: document.getElementById('artinfo-title'),
    artinfoCharacterSubtitle: document.getElementById('artinfo-character-subtitle'),
    artinfoPreviewImg: document.getElementById('artinfo-preview-img'),
    artinfoSeqBadge: document.getElementById('artinfo-seq-badge'),
    artinfoQualityBadge: document.getElementById('artinfo-quality-badge'),
    btnArtinfoOpenSource: document.getElementById('btn-artinfo-open-source'),
    btnArtinfoCopyUrl: document.getElementById('btn-artinfo-copy-url'),
    textArtinfoCopy: document.getElementById('text-artinfo-copy'),
    btnArtinfoFavorite: document.getElementById('btn-artinfo-favorite'),
    textArtinfoFav: document.getElementById('text-artinfo-fav'),
    btnArtinfoViewOrig: document.getElementById('btn-artinfo-view-orig'),
    btnArtinfoHide: document.getElementById('btn-artinfo-hide'),
    btnArtinfoBlacklist: document.getElementById('btn-artinfo-blacklist'),
    btnArtinfoReport: document.getElementById('btn-artinfo-report'),
    artinfoValFranchise: document.getElementById('artinfo-val-franchise'),
    artinfoValCharacter: document.getElementById('artinfo-val-character'),
    artinfoValId: document.getElementById('artinfo-val-id'),
    artinfoValProvider: document.getElementById('artinfo-val-provider'),
    artinfoValStrategy: document.getElementById('artinfo-val-strategy'),
    artinfoValResolution: document.getElementById('artinfo-val-resolution'),
    artinfoValRatio: document.getElementById('artinfo-val-ratio'),
    artinfoValFilesize: document.getElementById('artinfo-val-filesize'),
    artinfoValFavorites: document.getElementById('artinfo-val-favorites'),
    artinfoValViews: document.getElementById('artinfo-val-views'),
    artinfoValUploaddate: document.getElementById('artinfo-val-uploaddate'),
    artinfoValUploader: document.getElementById('artinfo-val-uploader'),
    artinfoValSource: document.getElementById('artinfo-val-source'),
    artinfoValSequence: document.getElementById('artinfo-val-sequence'),
    artinfoValQuality: document.getElementById('artinfo-val-quality'),
    artinfoValSafety: document.getElementById('artinfo-val-safety'),
    // Moderation Panel Elements
    settingModStrictMode: document.getElementById('setting-mod-strict-mode'),
    settingModAllowReview: document.getElementById('setting-mod-allow-review'),
    settingModAutoblockReported: document.getElementById('setting-mod-autoblock-reported'),
    settingModMinTags: document.getElementById('setting-mod-min-tags'),
    btnSaveModPolicy: document.getElementById('btn-save-mod-policy'),
    inputBlockType: document.getElementById('input-block-type'),
    inputBlockValue: document.getElementById('input-block-value'),
    inputBlockReason: document.getElementById('input-block-reason'),
    btnAddBlock: document.getElementById('btn-add-block'),
    blockedEntitiesList: document.getElementById('blocked-entities-list'),
    blockFilterPills: document.querySelectorAll('.block-filter-pill'),
    reviewQueueList: document.getElementById('review-queue-list'),
    // Composition & Focal Point Modal Elements
    modalComposition: document.getElementById('modal-composition'),
    btnCompClose: document.getElementById('btn-comp-close'),
    btnCompositionToggle: document.getElementById('btn-composition-toggle'),
    compCanvasWrapper: document.getElementById('comp-canvas-wrapper'),
    compCanvasImg: document.getElementById('comp-canvas-img'),
    compFocalReticle: document.getElementById('comp-focal-reticle'),
    reticleCoordBadge: document.getElementById('reticle-coord-badge'),
    compAspectBtns: document.querySelectorAll('.comp-aspect-btn'),
    compModeBtns: document.querySelectorAll('.comp-mode-btn'),
    compCheckBlurredBackdrop: document.getElementById('comp-check-blurred-backdrop'),
    compPresetBtns: document.querySelectorAll('.comp-preset-btn'),
    btnCompAddChar: document.getElementById('btn-comp-add-char'),
    compCharacterPinsList: document.getElementById('comp-character-pins-list'),
    btnCompSave: document.getElementById('btn-comp-save'),
    btnCompReset: document.getElementById('btn-comp-reset'),
    // Wallpaper History Explorer Elements
    btnHistoryOpen: document.getElementById('btn-history-open'),
    libTabHistoryBtn: document.getElementById('lib-tab-history-btn'),
    historyModal: document.getElementById('history-modal'),
    btnHistoryClose: document.getElementById('btn-history-close'),
    btnHistExportJson: document.getElementById('btn-hist-export-json'),
    btnHistExportCsv: document.getElementById('btn-hist-export-csv'),
    histSearchInput: document.getElementById('hist-search-input'),
    histSearchClear: document.getElementById('hist-search-clear'),
    btnHistFavToggle: document.getElementById('btn-hist-fav-toggle'),
    histFilterFranchise: document.getElementById('hist-filter-franchise'),
    histFilterDate: document.getElementById('hist-filter-date'),
    histFilterRes: document.getElementById('hist-filter-res'),
    histSortBy: document.getElementById('hist-sort-by'),
    btnHistRefresh: document.getElementById('btn-hist-refresh'),
    btnHistResetFilters: document.getElementById('btn-hist-reset-filters'),
    histTotalBadge: document.getElementById('hist-total-badge'),
    histResultsCount: document.getElementById('hist-results-count'),
    histActiveFiltersLabel: document.getElementById('hist-active-filters-label'),
    historyGrid: document.getElementById('history-grid'),
    historyEmpty: document.getElementById('history-empty'),
    btnHistFirst: document.getElementById('btn-hist-first'),
    btnHistPrev: document.getElementById('btn-hist-prev'),
    histCurrentPage: document.getElementById('hist-current-page'),
    histTotalPages: document.getElementById('hist-total-pages'),
    btnHistNext: document.getElementById('btn-hist-next'),
    btnHistLast: document.getElementById('btn-hist-last'),
    histPageSize: document.getElementById('hist-page-size')
  };

  // --- INITIALIZATION ---
  async function init() {
    setupEventListeners();
    setupDisplayListeners();
    initNetworkWatchers();
    detectDisplayTopology();
    setupClock();
    setupWeather();
    setupParticles();
    initSoundscapeAudio();
    applyPreferences();
    await checkBackendStatus();
    await loadConnectedMonitors();
    await loadFranchises();
    await loadLauncherConfig();
    await loadPersonalizationProfile();
    await loadQualitySettings();
    await loadSchedulerSettings();
    await loadSoundscapeSettings();
    await loadCompositionSettings();
    initArtworkInfoListeners();
    initCompositionListeners();
    initProviderSettings();
    initTagIntelligence();
    initPerformanceMonitoring();
    initHistoryExplorer();
    initModerationSystem();
    startIdleDetector();

    // Restore recent displayed history from backend across restarts
    await loadInitialHistory();

    // Start presentation with first wallpaper
    await displayNextWallpaper();
  }

  async function loadFranchises() {
    try {
      const res = await fetch(`${STATE.backendBase}/api/franchises`, { signal: AbortSignal.timeout(3000) });
      if (res.ok) {
        STATE.franchisesList = await res.json();
        updateCharacterDropdown();
      }
    } catch (_) {}
  }

  function updateCharacterDropdown() {
    if (!DOM.settingCharacter) return;
    const currentSlug = STATE.currentAnime;
    const franchise = STATE.franchisesList.find(f => f.slug === currentSlug || f.name.toLowerCase() === currentSlug.toLowerCase());

    DOM.settingCharacter.innerHTML = '<option value="all">✨ All Characters</option>';
    if (franchise && franchise.characters && franchise.characters.length > 0) {
      if (DOM.groupCharacter) DOM.groupCharacter.style.display = 'flex';
      for (const char of franchise.characters) {
        const opt = document.createElement('option');
        opt.value = char;
        opt.textContent = char;
        if (char === STATE.currentCharacter) opt.selected = true;
        DOM.settingCharacter.appendChild(opt);
      }
    } else {
      if (DOM.groupCharacter) DOM.groupCharacter.style.display = currentSlug === 'all' ? 'none' : 'flex';
    }
  }

  // Detect local backend server and obtain secure local session token
  async function checkBackendStatus() {
    const endpoints = [
      '/api/stats',
      'http://127.0.0.1:54321/api/stats',
      'http://localhost:54321/api/stats'
    ];

    for (const ep of endpoints) {
      try {
        const res = await fetch(ep, { signal: AbortSignal.timeout(1500) });
        if (res.ok) {
          STATE.backendBase = ep.replace('/api/stats', '');
          console.log('[Kuro] Connected to transactional backend at:', STATE.backendBase || window.location.origin);
          // Handshake local session token for state-changing endpoints
          try {
            const sRes = await fetch(`${STATE.backendBase}/api/v1/session`, { signal: AbortSignal.timeout(1500) });
            if (sRes.ok) {
              const sData = await sRes.json();
              STATE.sessionToken = sData.session_token;
            }
          } catch (_) {}
          return;
        }
      } catch (e) {}
    }
    console.warn('[Kuro] Running in disconnected client mode.');
  }

  // Secure authenticated POST helper for state-changing operations
  function backendPost(endpoint, bodyObj = {}) {
    const headers = { 'Content-Type': 'application/json' };
    const payload = Object.assign({}, bodyObj);
    if (STATE.sessionToken) {
      headers['X-Kuro-Token'] = STATE.sessionToken;
      payload.session_token = STATE.sessionToken;
    }
    return fetch(`${STATE.backendBase}${endpoint}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload)
    });
  }

  // Load recent displayed history so back-navigation works across page reloads
  async function loadInitialHistory() {
    try {
      const res = await fetch(`${STATE.backendBase}/api/history`, { signal: AbortSignal.timeout(2000) });
      if (res.ok) {
        const historyItems = await res.json();
        if (Array.isArray(historyItems) && historyItems.length > 0) {
          // Put in reverse chronological order for back-navigation
          STATE.sessionHistory = historyItems.reverse();
          STATE.sessionHistoryIndex = STATE.sessionHistory.length - 1;
        }
      }
    } catch (e) {
      console.warn('[Kuro] History load notice:', e);
    }
  }

  // --- UPGRADED CLOCK & CALENDAR SERVICE ---
  const TIMEZONE_LABELS = {
    'Asia/Tokyo': '🇯🇵 Tokyo',
    'America/New_York': '🇺🇸 New York',
    'America/Los_Angeles': '🇺🇸 Los Angeles',
    'Europe/London': '🇬🇧 London',
    'Europe/Paris': '🇫🇷 Paris',
    'Asia/Seoul': '🇰🇷 Seoul',
    'UTC': '🌐 UTC'
  };

  const JP_WEEKDAYS = ['日', '月', '火', '水', '木', '金', '土'];

  function formatDateByFormat(now, format) {
    const year = now.getFullYear();
    const monthIdx = now.getMonth();
    const date = now.getDate();
    const dayIdx = now.getDay();

    const fullWeekdays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const shortWeekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const fullMonths = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    const shortMonths = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    switch (format) {
      case 'standard':
        return `${shortWeekdays[dayIdx]} · ${shortMonths[monthIdx]} ${date}, ${year}`;
      case 'iso':
        const pad = (n) => String(n).padStart(2, '0');
        return `${year}-${pad(monthIdx + 1)}-${pad(date)} · ${shortWeekdays[dayIdx]}`;
      case 'anime_jp':
        return `${year}年${monthIdx + 1}月${date}日 (${JP_WEEKDAYS[dayIdx]})`;
      case 'full':
      default:
        return `${fullWeekdays[dayIdx]} · ${fullMonths[monthIdx]} ${date}, ${year}`;
    }
  }

  function setupClock() {
    function updateClock() {
      const now = new Date();
      let hours = now.getHours();
      const mins = String(now.getMinutes()).padStart(2, '0');
      const secs = String(now.getSeconds()).padStart(2, '0');
      let ampm = '';

      if (STATE.timeFormat === '12') {
        ampm = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12 || 12;
      }

      if (DOM.clockHoursMins) {
        DOM.clockHoursMins.textContent = `${String(hours).padStart(2, '0')}:${mins}`;
      }

      if (DOM.clockSeconds) {
        DOM.clockSeconds.textContent = secs;
        DOM.clockSeconds.classList.toggle('hide-seconds', !STATE.showSeconds);
      }

      if (DOM.clockAmPm) {
        DOM.clockAmPm.textContent = ampm;
        DOM.clockAmPm.style.display = STATE.timeFormat === '12' ? 'inline' : 'none';
      }

      // Date formatting
      if (DOM.clockDateText) {
        DOM.clockDateText.textContent = formatDateByFormat(now, STATE.dateFormat);
      }

      // Second Time Zone (Dual Clock)
      if (DOM.clockSecondTzRow) {
        if (STATE.secondTimeZone && STATE.secondTimeZone !== 'none') {
          DOM.clockSecondTzRow.classList.remove('hidden');
          const tzLabel = TIMEZONE_LABELS[STATE.secondTimeZone] || STATE.secondTimeZone;
          if (DOM.clockSecondTzLabel) DOM.clockSecondTzLabel.textContent = tzLabel;

          try {
            const is12 = STATE.timeFormat === '12';
            const options = {
              timeZone: STATE.secondTimeZone,
              hour: is12 ? 'numeric' : '2-digit',
              minute: '2-digit',
              hour12: is12
            };
            if (STATE.showSeconds) {
              options.second = '2-digit';
            }
            const timeStr = new Intl.DateTimeFormat('en-US', options).format(now);
            if (DOM.clockSecondTzTime) DOM.clockSecondTzTime.textContent = timeStr;
          } catch (_) {
            DOM.clockSecondTzRow.classList.add('hidden');
          }
        } else {
          DOM.clockSecondTzRow.classList.add('hidden');
        }
      }
    }

    updateClock();
    setInterval(updateClock, 1000);
  }

  // --- UPGRADED WEATHER SERVICE (Open-Meteo) ---
  const WMO_MAP = {
    0: { dayDesc: 'Sunny', nightDesc: 'Clear Night', dayIcon: '☀️', nightIcon: '🌙' },
    1: { dayDesc: 'Mainly Sunny', nightDesc: 'Mainly Clear', dayIcon: '🌤️', nightIcon: '🌌' },
    2: { dayDesc: 'Partly Cloudy', nightDesc: 'Partly Cloudy', dayIcon: '⛅', nightIcon: '☁️' },
    3: { dayDesc: 'Overcast', nightDesc: 'Overcast', dayIcon: '☁️', nightIcon: '☁️' },
    45: { dayDesc: 'Foggy', nightDesc: 'Foggy', dayIcon: '🌫️', nightIcon: '🌫️' },
    48: { dayDesc: 'Depositing Rime Fog', nightDesc: 'Rime Fog', dayIcon: '🌫️', nightIcon: '🌫️' },
    51: { dayDesc: 'Light Drizzle', nightDesc: 'Light Drizzle', dayIcon: '🌦️', nightIcon: '🌧️' },
    53: { dayDesc: 'Moderate Drizzle', nightDesc: 'Moderate Drizzle', dayIcon: '🌧️', nightIcon: '🌧️' },
    55: { dayDesc: 'Dense Drizzle', nightDesc: 'Dense Drizzle', dayIcon: '🌧️', nightIcon: '🌧️' },
    56: { dayDesc: 'Light Freezing Drizzle', nightDesc: 'Freezing Drizzle', dayIcon: '🌨️', nightIcon: '🌨️' },
    57: { dayDesc: 'Dense Freezing Drizzle', nightDesc: 'Freezing Drizzle', dayIcon: '🌨️', nightIcon: '🌨️' },
    61: { dayDesc: 'Slight Rain', nightDesc: 'Slight Rain', dayIcon: '🌧️', nightIcon: '🌧️' },
    63: { dayDesc: 'Moderate Rain', nightDesc: 'Moderate Rain', dayIcon: '🌧️', nightIcon: '🌧️' },
    65: { dayDesc: 'Heavy Rain', nightDesc: 'Heavy Rain', dayIcon: '🌧️', nightIcon: '🌧️' },
    66: { dayDesc: 'Light Freezing Rain', nightDesc: 'Freezing Rain', dayIcon: '🌨️', nightIcon: '🌨️' },
    67: { dayDesc: 'Heavy Freezing Rain', nightDesc: 'Freezing Rain', dayIcon: '🌨️', nightIcon: '🌨️' },
    71: { dayDesc: 'Slight Snow Fall', nightDesc: 'Slight Snow Fall', dayIcon: '❄️', nightIcon: '❄️' },
    73: { dayDesc: 'Moderate Snow Fall', nightDesc: 'Moderate Snow', dayIcon: '❄️', nightIcon: '❄️' },
    75: { dayDesc: 'Heavy Snow Fall', nightDesc: 'Heavy Snow Fall', dayIcon: '❄️', nightIcon: '❄️' },
    77: { dayDesc: 'Snow Grains', nightDesc: 'Snow Grains', dayIcon: '🌨️', nightIcon: '🌨️' },
    80: { dayDesc: 'Slight Rain Showers', nightDesc: 'Rain Showers', dayIcon: '🌦️', nightIcon: '🌧️' },
    81: { dayDesc: 'Moderate Showers', nightDesc: 'Moderate Showers', dayIcon: '🌧️', nightIcon: '🌧️' },
    82: { dayDesc: 'Violent Rain Showers', nightDesc: 'Violent Showers', dayIcon: '⛈️', nightIcon: '⛈️' },
    85: { dayDesc: 'Slight Snow Showers', nightDesc: 'Snow Showers', dayIcon: '🌨️', nightIcon: '🌨️' },
    86: { dayDesc: 'Heavy Snow Showers', nightDesc: 'Heavy Snow Showers', dayIcon: '❄️', nightIcon: '❄️' },
    95: { dayDesc: 'Thunderstorm', nightDesc: 'Thunderstorm', dayIcon: '⚡', nightIcon: '⚡' },
    96: { dayDesc: 'Thunderstorm with Slight Hail', nightDesc: 'Thunderstorm & Hail', dayIcon: '⛈️', nightIcon: '⛈️' },
    99: { dayDesc: 'Thunderstorm with Heavy Hail', nightDesc: 'Severe Thunderstorm', dayIcon: '⛈️', nightIcon: '⛈️' }
  };

  function formatSunTime(isoString, is12Hours) {
    if (!isoString) return '--:--';
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) {
        const parts = isoString.split('T');
        return parts[1] || isoString;
      }
      let h = d.getHours();
      const m = String(d.getMinutes()).padStart(2, '0');
      if (is12Hours) {
        const ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12 || 12;
        return `${h}:${m} ${ampm}`;
      }
      return `${String(h).padStart(2, '0')}:${m}`;
    } catch (_) {
      return '--:--';
    }
  }

  function applyWeatherDisplay(weatherData, cityName, isCached) {
    if (!weatherData || !weatherData.current) return;
    const current = weatherData.current;
    const isDay = current.is_day === 1;
    const code = current.weather_code != null ? current.weather_code : 0;
    const wmo = WMO_MAP[code] || { dayDesc: 'Clear', nightDesc: 'Clear Night', dayIcon: '☀️', nightIcon: '🌙' };

    const icon = isDay ? wmo.dayIcon : wmo.nightIcon;
    const desc = isDay ? wmo.dayDesc : wmo.nightDesc;
    const temp = Math.round(current.temperature_2m);
    const feels = Math.round(current.apparent_temperature != null ? current.apparent_temperature : current.temperature_2m);
    const humidity = current.relative_humidity_2m != null ? Math.round(current.relative_humidity_2m) : null;
    const windSpeed = current.wind_speed_10m != null ? Math.round(current.wind_speed_10m) : null;
    const windUnit = STATE.tempUnit === 'C' ? 'km/h' : 'mph';

    if (DOM.weatherTemp) DOM.weatherTemp.textContent = `${temp}°${STATE.tempUnit}`;
    if (DOM.weatherDesc) DOM.weatherDesc.textContent = desc;
    if (DOM.weatherIcon) DOM.weatherIcon.textContent = icon;
    if (DOM.weatherFeels) DOM.weatherFeels.textContent = `Feels ${feels}°${STATE.tempUnit}`;

    if (DOM.weatherCity) {
      DOM.weatherCity.textContent = isCached ? `${cityName} (Cached)` : cityName;
    }
    if (DOM.statWeatherLocation) {
      DOM.statWeatherLocation.textContent = `${cityName} (${isCached ? 'Cached' : 'Live'})`;
    }

    if (DOM.weatherHumidity && humidity != null) {
      DOM.weatherHumidity.textContent = `💧 ${humidity}%`;
    }
    if (DOM.weatherWind && windSpeed != null) {
      DOM.weatherWind.textContent = `💨 ${windSpeed} ${windUnit}`;
    }

    // Sunrise & Sunset from daily
    if (DOM.weatherSun && weatherData.daily && weatherData.daily.sunrise && weatherData.daily.sunset) {
      const sunriseTime = formatSunTime(weatherData.daily.sunrise[0], STATE.timeFormat === '12');
      const sunsetTime = formatSunTime(weatherData.daily.sunset[0], STATE.timeFormat === '12');
      DOM.weatherSun.textContent = `🌅 ${sunriseTime} · 🌇 ${sunsetTime}`;
    }
  }

  let weatherTimer = null;
  async function setupWeather() {
    clearTimeout(weatherTimer);

    // 1. Render offline weather cache immediately so there's zero wait time
    const rawCache = localStorage.getItem('kuro_weather_cache');
    let cacheParsed = null;
    if (rawCache) {
      try {
        cacheParsed = JSON.parse(rawCache);
        if (cacheParsed && cacheParsed.data) {
          applyWeatherDisplay(cacheParsed.data, cacheParsed.cityName || 'Local', true);
        }
      } catch (_) {}
    }

    // 2. Fetch fresh weather from Open-Meteo
    try {
      let lat = 28.61, lon = 77.23, cityName = 'Auto';

      if (STATE.customCity.trim()) {
        const geoRes = await fetch(
          `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(STATE.customCity.trim())}&count=1&language=en&format=json`,
          { signal: AbortSignal.timeout(4500) }
        );
        if (geoRes.ok) {
          const geoData = await geoRes.json();
          if (geoData.results && geoData.results.length > 0) {
            lat = geoData.results[0].latitude;
            lon = geoData.results[0].longitude;
            cityName = geoData.results[0].name;
            if (geoData.results[0].country) {
              cityName += `, ${geoData.results[0].country_code || geoData.results[0].country}`;
            }
          }
        }
      } else {
        // Automatic IP-based location detection with dual provider fallback
        let ipResolved = false;
        try {
          const ipRes = await fetch('https://ipapi.co/json/', { signal: AbortSignal.timeout(3000) });
          if (ipRes.ok) {
            const ipData = await ipRes.json();
            if (ipData.latitude && ipData.longitude) {
              lat = ipData.latitude;
              lon = ipData.longitude;
              cityName = ipData.city || 'Local';
              ipResolved = true;
            }
          }
        } catch (_) {}

        if (!ipResolved) {
          try {
            const ipwhoRes = await fetch('https://ipwho.is/', { signal: AbortSignal.timeout(3000) });
            if (ipwhoRes.ok) {
              const ipwhoData = await ipwhoRes.json();
              if (ipwhoData.success && ipwhoData.latitude && ipwhoData.longitude) {
                lat = ipwhoData.latitude;
                lon = ipwhoData.longitude;
                cityName = ipwhoData.city || 'Local';
                ipResolved = true;
              }
            }
          } catch (_) {}
        }
      }

      STATE.detectedCityName = cityName;

      // Query Open-Meteo with units
      const tempParam = STATE.tempUnit === 'F' ? 'fahrenheit' : 'celsius';
      const windParam = STATE.tempUnit === 'F' ? 'mph' : 'kmh';
      const weatherUrl = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,weather_code,wind_speed_10m&daily=sunrise,sunset&timezone=auto&temperature_unit=${tempParam}&wind_speed_unit=${windParam}`;

      const weatherRes = await fetch(weatherUrl, { signal: AbortSignal.timeout(6000) });
      if (weatherRes.ok) {
        const weatherData = await weatherRes.json();
        if (weatherData && weatherData.current) {
          applyWeatherDisplay(weatherData, cityName, false);

          // Save to offline cache
          localStorage.setItem('kuro_weather_cache', JSON.stringify({
            data: weatherData,
            cityName: cityName,
            timestamp: Date.now()
          }));
        }
      }
    } catch (err) {
      console.warn('[Kuro] Weather fetch error, using cached/fallback state:', err);
      // If we didn't have cache, show safe fallback
      if (!cacheParsed) {
        if (DOM.weatherTemp) DOM.weatherTemp.textContent = `21°${STATE.tempUnit}`;
        if (DOM.weatherDesc) DOM.weatherDesc.textContent = 'Clear Night';
        if (DOM.weatherIcon) DOM.weatherIcon.textContent = '🌙';
        if (DOM.weatherFeels) DOM.weatherFeels.textContent = `Feels 21°${STATE.tempUnit}`;
        if (DOM.weatherCity) DOM.weatherCity.textContent = 'Offline';
      }
    }

    // Schedule 15 minute automatic refresh
    weatherTimer = setTimeout(setupWeather, 15 * 60 * 1000);
  }

  // --- CONCURRENT IMAGE DECODING QUEUE (Limits simultaneous decodes to max 1) ---
  const ImageDecodeQueue = {
    running: 0,
    maxConcurrent: 1,
    queue: [],
    enqueue(fn) {
      return new Promise((resolve, reject) => {
        this.queue.push({ fn, resolve, reject });
        this.process();
      });
    },
    async process() {
      if (this.running >= this.maxConcurrent || this.queue.length === 0) return;
      this.running++;
      const { fn, resolve, reject } = this.queue.shift();
      try {
        const result = await fn();
        resolve(result);
      } catch (err) {
        reject(err);
      } finally {
        this.running--;
        this.process();
      }
    }
  };

  // --- OBJECT URL REGISTRY (Prevents browser memory leaks) ---
  const ObjectURLRegistry = {
    activeUrls: new Set(),
    create(blob) {
      const url = URL.createObjectURL(blob);
      this.activeUrls.add(url);
      return url;
    },
    revoke(url) {
      if (url && this.activeUrls.has(url)) {
        try { URL.revokeObjectURL(url); } catch (_) {}
        this.activeUrls.delete(url);
      }
    },
    revokeAll() {
      for (const url of this.activeUrls) {
        try { URL.revokeObjectURL(url); } catch (_) {}
      }
      this.activeUrls.clear();
    }
  };
  window.addEventListener('beforeunload', () => ObjectURLRegistry.revokeAll());

  // --- IMAGE PRELOADER (Off-thread GPU decode to eliminate frame stutter) ---
  function preloadImage(url) {
    const tStart = performance.now();
    let tLoaded = tStart;

    return new Promise((resolve, reject) => {
      const img = new Image();
      img.referrerPolicy = 'no-referrer';
      img.src = url;

      const onLoaded = async () => {
        tLoaded = performance.now();
        const loadDuration = Math.round(tLoaded - tStart);

        let decodeDuration = 0;
        if ('decode' in img) {
          try {
            await ImageDecodeQueue.enqueue(async () => {
              const tDecStart = performance.now();
              try {
                await img.decode();
              } catch (_) {}
              decodeDuration = Math.round(performance.now() - tDecStart);
            });
          } catch (_) {}
        }

        STATE.lastImageLoadMs = loadDuration;
        STATE.lastImageDecodeMs = decodeDuration;
        STATE.lastImageTotalMs = loadDuration + decodeDuration;

        // If diagnostics panel is open, update image time card immediately
        if (STATE.diagnosticsOpen && DOM.perfValImgTime) {
          DOM.perfValImgTime.textContent = STATE.lastImageTotalMs;
          if (DOM.perfSubImgTime) {
            DOM.perfSubImgTime.textContent = `Load: ${loadDuration}ms · Dec: ${decodeDuration}ms`;
          }
          if (DOM.perfImgDot) {
            const total = STATE.lastImageTotalMs;
            DOM.perfImgDot.className = `perf-card-status-dot ${total > 1500 ? 'dot-red' : total > 600 ? 'dot-yellow' : 'dot-green'}`;
          }
        }

        resolve(img);
      };

      if (img.complete && img.naturalWidth > 0) {
        onLoaded();
      } else {
        img.onload = onLoaded;
        img.onerror = () => reject(new Error('Image failed to load or decode'));
      }
    });
  }

  // --- DYNAMIC ACCENT COLOR EXTRACTION ---
  function extractAccentColor(img, fallbackColors) {
    // Avoid unnecessary image processing in Low Resource mode
    if (STATE.effectiveQualityProfile === 'low') {
      return { r: 56, g: 189, b: 248, hex: '#38bdf8' };
    }

    // In Balanced mode, prefer palette fallback if available to avoid canvas operations
    if (STATE.effectiveQualityProfile === 'balanced' && Array.isArray(fallbackColors) && fallbackColors.length > 0) {
      for (const hexColor of fallbackColors) {
        if (typeof hexColor === 'string' && hexColor.startsWith('#')) {
          const hex = hexColor.replace('#', '');
          const r = parseInt(hex.substring(0, 2), 16);
          const g = parseInt(hex.substring(2, 4), 16);
          const b = parseInt(hex.substring(4, 6), 16);
          return { r, g, b, hex: hexColor };
        }
      }
    }

    // 1. Try Wallhaven API palette first if provided
    if (Array.isArray(fallbackColors) && fallbackColors.length > 0) {
      for (const hexColor of fallbackColors) {
        if (typeof hexColor === 'string' && hexColor.startsWith('#')) {
          const hex = hexColor.replace('#', '');
          const r = parseInt(hex.substring(0, 2), 16);
          const g = parseInt(hex.substring(2, 4), 16);
          const b = parseInt(hex.substring(4, 6), 16);
          const max = Math.max(r, g, b);
          const min = Math.min(r, g, b);
          // Look for colors that are vibrant (not pitch black or muted grey)
          if (max > 80 && (max - min) > 28) {
            return { r, g, b, hex: hexColor };
          }
        }
      }
    }

    // 2. Off-screen micro-canvas color extraction from decoded image
    if (img && img.naturalWidth > 0) {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = 32;
        canvas.height = 32;
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        ctx.drawImage(img, 0, 0, 32, 32);
        const data = ctx.getImageData(0, 0, 32, 32).data;
        let bestColor = null;
        let bestScore = -1;

        for (let i = 0; i < data.length; i += 16) {
          const r = data[i];
          const g = data[i + 1];
          const b = data[i + 2];
          const max = Math.max(r, g, b);
          const min = Math.min(r, g, b);
          const saturation = max === 0 ? 0 : (max - min) / max;
          const lightness = (max + min) / 510;

          if (lightness > 0.25 && lightness < 0.85 && saturation > 0.22) {
            const score = saturation * 1.6 + (1 - Math.abs(lightness - 0.55));
            if (score > bestScore) {
              bestScore = score;
              const toHex = (n) => n.toString(16).padStart(2, '0');
              bestColor = { r, g, b, hex: `#${toHex(r)}${toHex(g)}${toHex(b)}` };
            }
          }
        }
        if (bestColor) return bestColor;
      } catch (_) {}
    }

    return { r: 56, g: 189, b: 248, hex: '#38bdf8' }; // Default sky cyan
  }

  // --- INTELLIGENT CHARACTER FOCAL POINT CALCULATION ---
  function calculateFocalPoint(img) {
    if (STATE.focalPointMode === 'top') {
      return { x: 50, y: 30 };
    }
    if (STATE.focalPointMode === 'center') {
      return { x: 50, y: 50 };
    }

    // When automatic face detection is unavailable, use honest center positioning
    // rather than pretending that the focal point has been detected.
    // Users can adjust and persist exact focal coordinates via the Manual Framing Editor (Key: O).
    if (STATE.compositionSettings && STATE.compositionSettings.auto_focal_protection) {
      // Safe upper-center rule-of-thirds default (50%, 35%) to protect head/face regions across portrait & landscape
      return { x: 50, y: 35 };
    }

    return { x: 50, y: 50 };
  }

  // --- MULTI-MONITOR TOPOLOGY & RATIO RESOLUTION ---
  function getEffectiveRatio() {
    if (STATE.aspectRatio && STATE.aspectRatio !== 'auto') {
      return STATE.aspectRatio;
    }
    // If a specific target monitor is selected in multi-monitor setup
    if (STATE.targetMonitor && STATE.targetMonitor !== 'auto') {
      const mon = STATE.connectedMonitors.find(m => m.name === STATE.targetMonitor);
      if (mon && mon.ratio) return mon.ratio;
    }
    // Fall back to active viewport's physical orientation
    return STATE.currentTopology.orientation || 'landscape';
  }

  function detectDisplayTopology() {
    const width = window.innerWidth;
    const height = window.innerHeight;
    const dpr = window.devicePixelRatio || 1;
    const physWidth = Math.round(width * dpr);
    const physHeight = Math.round(height * dpr);
    const ratio = width / Math.max(1, height);

    let orientation = 'landscape';
    if (ratio < 0.95) {
      orientation = 'portrait';
    } else if (ratio >= 2.05) {
      orientation = 'ultrawide';
    } else {
      orientation = 'landscape';
    }

    const prevOrientation = STATE.currentTopology ? STATE.currentTopology.orientation : null;
    STATE.currentTopology = {
      orientation,
      width,
      height,
      physWidth,
      physHeight,
      dpr,
      ratio
    };

    // Apply layout classes to body for responsive styling
    document.body.classList.toggle('aspect-portrait', orientation === 'portrait');
    document.body.classList.toggle('aspect-ultrawide', orientation === 'ultrawide');
    document.body.classList.toggle('aspect-landscape', orientation === 'landscape');

    // Update settings statistics
    if (DOM.statViewportRes) {
      const ratioName = orientation === 'portrait' ? '9:16' : (orientation === 'ultrawide' ? '21:9' : '16:9');
      DOM.statViewportRes.textContent = `${width} × ${height} (${physWidth} × ${physHeight} phys · ${ratioName})`;
    }
    if (DOM.statDpiScale) {
      DOM.statDpiScale.textContent = `${Math.round(dpr * 100)}% (${dpr.toFixed(2)}x)`;
    }

    // Adapt particle canvas dimensions if initialized
    if (DOM.ambientCanvas) {
      DOM.ambientCanvas.width = width;
      DOM.ambientCanvas.height = height;
    }

    // If orientation shifted across displays or rotation
    if (prevOrientation && prevOrientation !== orientation) {
      showToast(`Orientation adapted: ${orientation.toUpperCase()} (${width}×${height})`);
      if (STATE.aspectRatio === 'auto') {
        displayNextWallpaper();
      }
    }

    return STATE.currentTopology;
  }

  let monitorPollTimer = null;
  async function loadConnectedMonitors() {
    try {
      const res = await fetch(`${STATE.backendBase}/api/monitors`, { signal: AbortSignal.timeout(3500) });
      if (res.ok) {
        const data = await res.json();
        STATE.connectedMonitors = data.monitors || [];

        // Update target monitor dropdown
        if (DOM.settingMonitor) {
          const currentVal = STATE.targetMonitor;
          DOM.settingMonitor.innerHTML = '<option value="auto">Auto (Match Active Viewport)</option>';

          let foundTarget = (currentVal === 'auto');
          for (const mon of STATE.connectedMonitors) {
            const opt = document.createElement('option');
            opt.value = mon.name;
            const primaryBadge = mon.primary ? ' [Primary]' : '';
            const profileText = mon.profile || `${mon.width}×${mon.height}`;
            opt.textContent = `${mon.name}: ${profileText} (${mon.orientation})${primaryBadge}`;
            if (mon.name === currentVal) {
              opt.selected = true;
              foundTarget = true;
            }
            DOM.settingMonitor.appendChild(opt);
          }

          // Monitor disconnect & reconnect detection
          if (currentVal !== 'auto') {
            if (!foundTarget) {
              if (!STATE.wasMonitorDisconnected) {
                STATE.wasMonitorDisconnected = true;
                showToast(`Target monitor '${currentVal}' disconnected. Falling back to active viewport.`);
                if (DOM.statActiveMonitor) DOM.statActiveMonitor.textContent = 'Auto (Disconnected Fallback)';
              }
            } else {
              if (STATE.wasMonitorDisconnected) {
                STATE.wasMonitorDisconnected = false;
                showToast(`Target monitor '${currentVal}' reconnected.`);
              }
              const activeMon = STATE.connectedMonitors.find(m => m.name === currentVal);
              if (DOM.statActiveMonitor && activeMon) {
                DOM.statActiveMonitor.textContent = `${activeMon.name} (${activeMon.profile || `${activeMon.width}×${activeMon.height}`})`;
              }
            }
          } else {
            if (DOM.statActiveMonitor) {
              const count = STATE.connectedMonitors.length;
              DOM.statActiveMonitor.textContent = `Auto (${count} display${count === 1 ? '' : 's'} connected)`;
            }
          }
        }
      }
    } catch (_) {}

    // Periodic check every 10s for monitor hotplugging
    clearTimeout(monitorPollTimer);
    monitorPollTimer = setTimeout(loadConnectedMonitors, 10000);
  }

  function setupDisplayListeners() {
    let resizeDebounce = null;
    const handleResize = () => {
      clearTimeout(resizeDebounce);
      resizeDebounce = setTimeout(() => {
        detectDisplayTopology();
      }, 150);
    };

    window.addEventListener('resize', handleResize, { passive: true });
    window.addEventListener('orientationchange', handleResize, { passive: true });
    window.addEventListener('focus', () => {
      detectDisplayTopology();
      loadConnectedMonitors();
    });

    // Watch for Windows DPI scaling and browser zoom changes
    function watchDpi() {
      const dpr = window.devicePixelRatio || 1;
      const mediaQuery = window.matchMedia(`(resolution: ${dpr}dppx)`);
      const onChange = () => {
        detectDisplayTopology();
        watchDpi(); // Re-arm with new DPR
      };
      if (mediaQuery.addEventListener) {
        mediaQuery.addEventListener('change', onChange, { once: true });
      } else if (mediaQuery.addListener) {
        mediaQuery.addListener(onChange);
      }
    }
    watchDpi();
  }

  // --- TRANSACTIONAL CANDIDATE FETCHING ---
  async function fetchCandidate() {
    DOM.bufferIndicator.classList.remove('hidden');
    try {
      const charParam = (STATE.currentCharacter && STATE.currentCharacter !== 'all') ? `&character=${encodeURIComponent(STATE.currentCharacter)}` : '';
      const effectiveRatio = getEffectiveRatio();
      const url = `${STATE.backendBase}/api/next?anime=${encodeURIComponent(STATE.currentAnime)}${charParam}&ratio=${effectiveRatio}`;
      const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
      if (res.ok) {
        const data = await res.json();
        DOM.bufferIndicator.classList.add('hidden');
        return data;
      }
    } catch (e) {
      console.warn('[Kuro] Candidate fetch error:', e);
    }
    DOM.bufferIndicator.classList.add('hidden');
    return null;
  }

  // Confirm display on backend (Transitions RESERVED -> DISPLAYED in SQLite)
  async function confirmDisplayedOnBackend(id, token) {
    try {
      await backendPost('/api/confirm-display', { id: id, reservation_token: token });
    } catch (e) {
      console.warn('[Kuro] Confirm display error:', e);
    }
  }

  // Report image load failure (Transitions RESERVED -> FAILED in SQLite)
  async function reportDisplayFailed(id, token, reason) {
    try {
      await backendPost('/api/display-failed', { id: id, reservation_token: token, reason: reason });
    } catch (e) {
      console.warn('[Kuro] Report failure error:', e);
    }
  }

  // --- EXHAUSTION HANDLING ---
  function handleCollectionExhausted(data) {
    cancelAnimationFrame(STATE.progressRaf);
    clearTimeout(STATE.timer);
    DOM.exhaustionTitle.textContent = `Collection Exhausted: ${data.anime || 'Anime'}`;
    DOM.exhaustionMsg.textContent = `Every single wallpaper in the '${data.anime}' collection has been viewed. As requested, wallpapers are never repeated. You can switch to another franchise or reset your history in settings.`;
    DOM.exhaustionOverlay.classList.remove('hidden');
  }

  function rotateToNextFranchise() {
    if (!STATE.franchisesList || STATE.franchisesList.length === 0) return;
    STATE.currentFranchiseRotIdx = ((STATE.currentFranchiseRotIdx || 0) + 1) % STATE.franchisesList.length;
    const nextF = STATE.franchisesList[STATE.currentFranchiseRotIdx];
    if (nextF && nextF.slug) {
      STATE.currentAnime = nextF.slug;
      if (DOM.settingAnime) DOM.settingAnime.value = nextF.slug;
      localStorage.setItem('kuro_anime', nextF.slug);
      DOM.quickMoods.forEach(b => {
        b.classList.toggle('active', b.dataset.anime === nextF.slug);
      });
      updateCharacterDropdown();
      showToast(`🔄 Rotating Franchise: ${nextF.name || nextF.slug}`);
    }
  }

  // --- TRANSITION & DISPLAY ENGINE ---
  async function displayNextWallpaper() {
    if (STATE.isTransitioning) return;
    STATE.isTransitioning = true;

    clearTimeout(STATE.timer);
    cancelAnimationFrame(STATE.progressRaf);

    // Forward navigation in existing session history
    if (STATE.sessionHistoryIndex < STATE.sessionHistory.length - 1) {
      STATE.sessionHistoryIndex++;
      const existing = STATE.sessionHistory[STATE.sessionHistoryIndex];
      await applyWallpaper(existing);
      STATE.isTransitioning = false;
      startSlideTimer();
      return;
    }

    // Franchise Rotation Check before fetching new candidate
    if (STATE.schedulerStrategy === 'franchise_rotation') {
      STATE.franchiseSlideCount = (STATE.franchiseSlideCount || 0) + 1;
      const rotInterval = Math.max(1, STATE.franchiseRotationInterval || 5);
      if (STATE.franchiseSlideCount >= rotInterval) {
        STATE.franchiseSlideCount = 0;
        rotateToNextFranchise();
      }
    }

    // Attempt to retrieve and display a fresh candidate
    let attempts = 0;
    while (attempts < 3) {
      attempts++;
      const candidate = await fetchCandidate();

      if (!candidate) {
        showToast('Waiting for stream connection...');
        await new Promise(r => setTimeout(r, 2000));
        continue;
      }

      // Check if collection is exhausted
      if (candidate.exhausted) {
        handleCollectionExhausted(candidate);
        STATE.isTransitioning = false;
        return;
      }

      // Preload image to guarantee successful rendering before committing
      try {
        const preloadedImg = await preloadImage(candidate.url);
        candidate._preloadedImg = preloadedImg;
      } catch (err) {
        console.warn(`[Kuro] Wallpaper ${candidate.id} failed loading:`, err);
        await reportDisplayFailed(candidate.id, candidate.reservation_token, err.message);
        continue; // Fetch next candidate
      }

      // Successful render
      await applyWallpaper(candidate);

      // Confirm to SQLite backend: RESERVED -> DISPLAYED
      if (candidate.reservation_token) {
        await confirmDisplayedOnBackend(candidate.id, candidate.reservation_token);
      }

      // Append to session history for back/forward navigation
      STATE.sessionHistory.push(candidate);
      STATE.sessionHistoryIndex = STATE.sessionHistory.length - 1;

      // Update stats badge
      updateStats();

      STATE.isTransitioning = false;
      startSlideTimer();
      return;
    }

    STATE.isTransitioning = false;
    startSlideTimer();
  }

  async function displayPrevWallpaper() {
    if (STATE.isTransitioning) return;

    if (STATE.sessionHistoryIndex > 0) {
      STATE.isTransitioning = true;
      clearTimeout(STATE.timer);
      cancelAnimationFrame(STATE.progressRaf);

      // Record dwell for currently leaving wallpaper before moving back
      recordDwellForCurrentWallpaper(false);

      STATE.sessionHistoryIndex--;
      const prevItem = STATE.sessionHistory[STATE.sessionHistoryIndex];

      // Record revisit interaction event
      if (prevItem) {
        backendPost('/api/interaction/revisit', {
          id: prevItem.id,
          anime: prevItem.anime || '',
          character: prevItem.character || ''
        }).catch(() => {});
      }

      await applyWallpaper(prevItem);

      STATE.isTransitioning = false;
      startSlideTimer();
    } else {
      showToast('At the beginning of session history.');
    }
  }

  // --- MOTION & TRANSITION ORCHESTRATION ---
  function isReducedMotionActive() {
    if (STATE.reducedMotion) return true;
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  const MOTION_VARIANTS = [
    'zoom-in',
    'zoom-out',
    'pan-left',
    'pan-right',
    'pan-up',
    'pan-down'
  ];

  function selectMotionVariant() {
    if (isReducedMotionActive() || STATE.motionStyle === 'none') {
      return 'none';
    }
    if (STATE.motionStyle !== 'random') {
      return STATE.motionStyle;
    }
    let nextIdx;
    do {
      nextIdx = Math.floor(Math.random() * MOTION_VARIANTS.length);
    } while (nextIdx === STATE.lastMotionIndex && MOTION_VARIANTS.length > 1);
    STATE.lastMotionIndex = nextIdx;
    return MOTION_VARIANTS[nextIdx];
  }

  const TRANSITION_STYLES = [
    'crossfade',
    'cinematic',
    'slow-zoom',
    'pan-dissolve'
  ];

  function selectTransitionStyle() {
    if (isReducedMotionActive()) {
      return 'crossfade';
    }
    if (STATE.transitionStyle === 'instant') {
      return 'instant';
    }
    if (STATE.transitionStyle !== 'random') {
      return STATE.transitionStyle;
    }
    let nextIdx;
    do {
      nextIdx = Math.floor(Math.random() * TRANSITION_STYLES.length);
    } while (nextIdx === STATE.lastTransitionIndex && TRANSITION_STYLES.length > 1);
    STATE.lastTransitionIndex = nextIdx;
    return TRANSITION_STYLES[nextIdx];
  }

  function recordDwellForCurrentWallpaper(explicitSkip = false) {
    if (!STATE.currentWallpaper || !STATE.currentWallpaperStartTime) return;
    const dwellSec = Math.max(0.1, (performance.now() - STATE.currentWallpaperStartTime) / 1000);
    const wasSkipped = explicitSkip || (dwellSec < 5.0);
    const wp = STATE.currentWallpaper;

    backendPost('/api/interaction/dwell', {
      id: wp.id,
      dwell_seconds: parseFloat(dwellSec.toFixed(2)),
      was_skipped: wasSkipped,
      anime: wp.anime || '',
      character: wp.character || ''
    }).catch(() => {});

    STATE.currentWallpaperStartTime = null;
  }

  async function applyWallpaper(wallpaper) {
    if (STATE.currentWallpaper && STATE.currentWallpaperStartTime) {
      recordDwellForCurrentWallpaper(STATE.wasExplicitlySkipped);
      STATE.wasExplicitlySkipped = false;
    }
    STATE.currentWallpaper = wallpaper;
    STATE.currentWallpaperStartTime = performance.now();
    STATE.currentSessionSequence++;

    const incomingLayer = STATE.activeLayer === 'a' ? DOM.layerB : DOM.layerA;
    const outgoingLayer = STATE.activeLayer === 'a' ? DOM.layerA : DOM.layerB;

    const motion = selectMotionVariant();
    const transition = selectTransitionStyle();
    const isInstant = transition === 'instant';
    const durationSec = isInstant ? 0.05 : STATE.transitionDuration;

    // Dynamically synchronize CSS custom properties for hardware compositing
    document.documentElement.style.setProperty('--transition-duration', `${durationSec}s`);
    document.documentElement.style.setProperty('--motion-duration', `${Math.max(STATE.intervalSeconds * 1.5, 35)}s`);

    // Resolve intelligent composition & focal point protection
    const comp = wallpaper.composition || {};
    const orientation = getEffectiveRatio();
    let effectiveMode = 'fill';
    if (orientation === 'portrait') {
      effectiveMode = comp.portrait_display_mode || comp.display_mode || (STATE.compositionSettings && STATE.compositionSettings.default_mode_portrait) || 'fit';
    } else if (orientation === 'ultrawide') {
      effectiveMode = comp.landscape_display_mode || comp.display_mode || (STATE.compositionSettings && STATE.compositionSettings.default_mode_ultrawide) || 'fill';
    } else {
      effectiveMode = comp.landscape_display_mode || comp.display_mode || (STATE.compositionSettings && STATE.compositionSettings.default_mode_landscape) || 'fill';
    }

    let focal = { x: 50.0, y: 50.0 };
    if (comp.focal_x != null && comp.focal_y != null) {
      focal = { x: comp.focal_x, y: comp.focal_y };
    } else {
      focal = calculateFocalPoint(wallpaper._preloadedImg);
    }
    STATE.currentComposition = {
      wallpaper_id: wallpaper.id,
      focal_x: focal.x,
      focal_y: focal.y,
      display_mode: effectiveMode,
      blurred_background: comp.blurred_background !== false,
      characters: comp.characters || []
    };

    // 1. Reset incoming layer to base class and inject preloaded wallpaper URL
    incomingLayer.className = 'wallpaper-layer';
    incomingLayer.style.backgroundImage = `url("${wallpaper.url}")`;
    incomingLayer.style.setProperty('--focal-x', `${focal.x}%`);
    incomingLayer.style.setProperty('--focal-y', `${focal.y}%`);
    incomingLayer.classList.add(`mode-${effectiveMode}`);

    const blurEnabled = STATE.compositionSettings ? STATE.compositionSettings.blurred_backdrop_enabled !== false : true;
    if ((effectiveMode === 'fit' || effectiveMode === 'original') && comp.blurred_background !== false && blurEnabled) {
      incomingLayer.classList.add('has-backdrop');
    }

    // Synchronize inner foreground and backdrop if present in DOM
    const inFore = incomingLayer.querySelector('.wallpaper-foreground');
    const inBack = incomingLayer.querySelector('.wallpaper-backdrop');
    if (inFore) inFore.style.backgroundImage = `url("${wallpaper.url}")`;
    if (inBack) inBack.style.backgroundImage = `url("${wallpaper.url}")`;

    // 2. Set preparation spatial transforms for incoming animations
    if (transition === 'slow-zoom') {
      incomingLayer.classList.add('prep-slow-zoom');
    } else if (transition === 'pan-dissolve') {
      incomingLayer.classList.add('prep-pan-dissolve');
    } else if (isInstant) {
      incomingLayer.classList.add('transition-instant');
    }

    // 3. Force browser layout reflow to register initial transform prior to transition
    void incomingLayer.offsetWidth;

    // 4. Activate incoming layer and initiate smooth GPU-composited transition
    incomingLayer.classList.add('active');

    if (transition === 'slow-zoom') {
      incomingLayer.classList.add('transition-slow-zoom');
    } else if (transition === 'pan-dissolve') {
      incomingLayer.classList.add('transition-pan-dissolve');
    }

    // 5. Apply smooth, continuous Ken Burns motion to incoming layer
    if (motion && motion !== 'none') {
      incomingLayer.classList.add(`motion-${motion}`);
    } else {
      incomingLayer.classList.add('motion-none');
    }

    // 6. Handle outgoing layer fade (cinematic blackout dip or seamless crossfade)
    if (transition === 'cinematic') {
      outgoingLayer.classList.add('cinematic-fade-out');
    } else {
      outgoingLayer.classList.add('fading-out');
    }
    outgoingLayer.classList.remove('active');

    // 7. Swap active layer pointer
    STATE.activeLayer = STATE.activeLayer === 'a' ? 'b' : 'a';

    // 8. Clean up outgoing layer after transition duration completes (no DOM reconstruction)
    const cleanupDelay = Math.round(durationSec * 1000) + 120;
    setTimeout(() => {
      outgoingLayer.className = 'wallpaper-layer';
      outgoingLayer.style.backgroundImage = '';
      outgoingLayer.style.removeProperty('--focal-x');
      outgoingLayer.style.removeProperty('--focal-y');
      outgoingLayer.classList.remove('has-backdrop', 'mode-fill', 'mode-fit', 'mode-original', 'prep-slow-zoom', 'transition-slow-zoom', 'prep-pan-dissolve', 'transition-pan-dissolve', 'transition-instant');
      const outFore = outgoingLayer.querySelector('.wallpaper-foreground');
      const outBack = outgoingLayer.querySelector('.wallpaper-backdrop');
      if (outFore) outFore.style.backgroundImage = '';
      if (outBack) outBack.style.backgroundImage = '';
    }, cleanupDelay);

    // 9. Extract dynamic accent color from wallpaper artwork
    const accent = extractAccentColor(wallpaper._preloadedImg, wallpaper.colors);
    STATE.extractedAccent = accent;
    document.documentElement.style.setProperty('--dynamic-accent', `rgb(${accent.r}, ${accent.g}, ${accent.b})`);
    document.documentElement.style.setProperty('--dynamic-accent-glow', `rgba(${accent.r}, ${accent.g}, ${accent.b}, 0.28)`);
    document.documentElement.style.setProperty('--dynamic-accent-subtle', `rgba(${accent.r}, ${accent.g}, ${accent.b}, 0.12)`);

    // 10. Update metadata HUD across zones
    DOM.tagRes.textContent = wallpaper.resolution || 'High Res';
    DOM.tagMood.textContent = wallpaper.anime || 'Popular Anime';
    if (DOM.tagCharacter) {
      DOM.tagCharacter.textContent = wallpaper.character ? `· ${wallpaper.character}` : '';
    }
    if (DOM.tagPalette) {
      DOM.tagPalette.textContent = accent.hex.toUpperCase();
    }
    if (DOM.tagQuality) {
      const q = wallpaper.quality_score != null ? Number(wallpaper.quality_score) : 75.0;
      const tech = wallpaper.technical_score != null ? Number(wallpaper.technical_score) : q;
      const pop = wallpaper.popularity_score != null ? Number(wallpaper.popularity_score) : q;
      DOM.tagQuality.textContent = `★ ${Math.round(q)}`;
      DOM.tagQuality.title = `Quality Score: ${q.toFixed(1)}/100\n• Technical Fidelity: ${tech.toFixed(1)}/100\n• Community Popularity: ${pop.toFixed(1)}/100\n(Subjective artistic quality is unmeasured)`;
    }
    DOM.btnDownload.href = wallpaper.url;
    if (DOM.dashStatRatio) {
      DOM.dashStatRatio.textContent = wallpaper.ratio || '16:9';
    }

    // Offline metadata indicator badge
    if (DOM.metaOfflineBadge) {
      if (wallpaper.level === 3 || wallpaper.source === 'Curated Offline') {
        DOM.metaOfflineBadge.textContent = '⚡ Curated Offline';
        DOM.metaOfflineBadge.classList.remove('hidden');
      } else if (wallpaper.level === 2 || wallpaper.source === 'Local Cache') {
        DOM.metaOfflineBadge.textContent = '⚡ Local Cache';
        DOM.metaOfflineBadge.classList.remove('hidden');
      } else if (wallpaper.offline || STATE.isOffline) {
        DOM.metaOfflineBadge.textContent = '⚡ Offline Stream';
        DOM.metaOfflineBadge.classList.remove('hidden');
      } else {
        DOM.metaOfflineBadge.classList.add('hidden');
      }
    }

    // OLED dynamic anti-burn-in shift on wallpaper change
    repositionHudAndWidgets();
    evaluateNightMode();

    // 11. Cinematic Mode: Reveal metadata temporarily (4.5s) then fade out
    if (STATE.displayMode === 'cinematic' && DOM.hudBottomLeft) {
      DOM.hudBottomLeft.classList.add('cinematic-reveal');
      clearTimeout(STATE.cinematicRevealTimer);
      STATE.cinematicRevealTimer = setTimeout(() => {
        DOM.hudBottomLeft.classList.remove('cinematic-reveal');
      }, 4500);
    }

    // Favorite state
    const isFav = STATE.favorites.some(f => f.id === wallpaper.id);
    DOM.btnFavorite.classList.toggle('favorited', isFav);
    if (DOM.favLabel) DOM.favLabel.textContent = isFav ? 'Favorited' : 'Favorite';

    // Reactive live updates for open modals while slideshow keeps playing
    if (STATE.artworkInfoModalOpen) {
      populateArtworkInfo(wallpaper);
    }
    if (STATE.compositionModalOpen) {
      populateCompositionModal(wallpaper);
    }
  }

  // --- OFFLINE & NETWORK RESILIENCE ---
  function initNetworkWatchers() {
    window.addEventListener('online', async () => {
      console.log('[Kuro] Browser network connection established.');
      STATE.isOffline = false;
      showToast('🌐 Internet connection restored: Live stream active');
      if (DOM.networkPill) DOM.networkPill.classList.add('hidden');
      await updateStats();
    });

    window.addEventListener('offline', () => {
      console.log('[Kuro] Browser entered offline mode.');
      STATE.isOffline = true;
      showToast('⚡ Offline Mode: Playing from Local Cache & Curated Collection');
      if (DOM.networkPill) DOM.networkPill.classList.remove('hidden');
      updateStats();
    });

    // Periodic sync every 12 seconds with local server status endpoint
    setInterval(async () => {
      try {
        const res = await fetch(`${STATE.backendBase}/api/status`);
        if (res.ok) {
          const stats = await res.json();
          const wasOffline = STATE.isOffline;
          STATE.isOffline = !stats.online;
          if (wasOffline && stats.online) {
            showToast('🌐 Network reconnected: Live Stream active');
          }
          if (DOM.networkPill) {
            if (STATE.isOffline) {
              DOM.networkPill.classList.remove('hidden');
            } else {
              DOM.networkPill.classList.add('hidden');
            }
          }
        }
      } catch (_) {}
    }, 12000);
  }

  async function updateStats(wallpaper) {
    try {
      const res = await fetch(`${STATE.backendBase}/api/stats`);
      if (res.ok) {
        const stats = await res.json();
        const seenCount = stats.displayed_count || STATE.sessionHistory.length;
        const favsCount = stats.favorites_count || STATE.favorites.length;
        
        STATE.isOffline = !stats.online;
        const item = wallpaper || STATE.currentWallpaper || {};
        const level = item.level || stats.active_level || (STATE.isOffline ? 3 : 1);

        if (DOM.statsBadge) {
          DOM.statsBadge.className = `stream-badge level-${level}`;
          if (level === 3) {
            DOM.statsBadge.textContent = `CURATED · #${seenCount}`;
          } else if (level === 2) {
            DOM.statsBadge.textContent = `CACHED · #${seenCount}`;
          } else {
            DOM.statsBadge.textContent = `LIVE · #${seenCount}`;
          }
        }

        if (DOM.networkPill) {
          if (STATE.isOffline || !stats.online) {
            DOM.networkPill.classList.remove('hidden');
            DOM.networkPill.textContent = level === 3 ? '⚡ OFFLINE · CURATED' : '⚡ OFFLINE · CACHED';
          } else {
            DOM.networkPill.classList.add('hidden');
          }
        }

        DOM.statTotalSeen.textContent = seenCount;
        DOM.statFavoritesCount.textContent = favsCount;
        if (DOM.dashStatSeen) DOM.dashStatSeen.textContent = seenCount;
        if (DOM.dashStatFavs) DOM.dashStatFavs.textContent = favsCount;
      }
    } catch (_) {}
  }

  // --- INTELLIGENT SLIDESHOW SCHEDULING ENGINE ---
  function calculateEffectiveSlideDuration(wallpaper) {
    if (STATE.schedulerStrategy === 'manual') {
      return Infinity;
    }

    let baseDuration = STATE.schedulerFixedSec || STATE.intervalSeconds || 30;

    if (STATE.schedulerStrategy === 'random') {
      const min = Math.max(5, STATE.schedulerRandMin || 15);
      const max = Math.max(min, STATE.schedulerRandMax || 60);
      baseDuration = Math.floor(Math.random() * (max - min + 1)) + min;
    } else if (STATE.schedulerStrategy === 'time_of_day') {
      const currentHour = new Date().getHours();
      if (currentHour >= 8 && currentHour < 17) {
        baseDuration = STATE.schedulerDaySec || 25;
      } else if (currentHour >= 17 && currentHour < 22) {
        baseDuration = STATE.schedulerEveSec || 35;
      } else {
        baseDuration = STATE.schedulerNightSec || 60;
      }
    }

    // Display mode adjustments
    if (STATE.displayMode === 'cinematic') {
      const cinSec = STATE.schedulerCinematicSec || 45;
      baseDuration = Math.max(baseDuration, cinSec);
    } else if (STATE.displayMode === 'dashboard') {
      const dashSec = STATE.schedulerDashboardSec || 20;
      baseDuration = Math.min(baseDuration, dashSec);
    }

    // Quality weighting & favorite bonus
    const applyQuality = (STATE.schedulerStrategy === 'quality_weighted') || STATE.schedulerQualityBonus;
    if (applyQuality && wallpaper) {
      let multiplier = 1.0;
      const q = typeof wallpaper.quality_score === 'number' ? wallpaper.quality_score : null;
      if (q !== null && !isNaN(q)) {
        if (q >= 70) {
          multiplier += ((q - 70.0) / 30.0) * 0.40;
        } else if (q < 40) {
          multiplier -= ((40.0 - q) / 40.0) * 0.20;
        }
      }
      baseDuration = baseDuration * multiplier;

      const isFav = wallpaper.favorite || wallpaper.is_favorite || (Array.isArray(STATE.favorites) && STATE.favorites.some(f => f.id === wallpaper.id));
      if (isFav) {
        baseDuration += 10.0;
      }
    }

    // Enforce bounds: 5s to 600s
    return Math.max(5, Math.min(600, Math.round(baseDuration * 10) / 10));
  }

  // --- SLIDESHOW TIMER & PROGRESS ANIMATION ---
  function startSlideTimer() {
    clearTimeout(STATE.timer);
    cancelAnimationFrame(STATE.progressRaf);
    STATE.savedElapsed = 0;
    STATE.isPausedForHidden = false;

    if (STATE.isPaused || STATE.schedulerStrategy === 'manual') {
      if (DOM.slideProgress) DOM.slideProgress.style.width = '0%';
      if (DOM.progressTimerText) {
        DOM.progressTimerText.textContent = STATE.isPaused ? 'Paused' : 'Manual Mode';
      }
      return;
    }

    if (STATE.isTransitioning) {
      return;
    }

    const durationSec = calculateEffectiveSlideDuration(STATE.currentWallpaper);
    if (!isFinite(durationSec)) {
      if (DOM.slideProgress) DOM.slideProgress.style.width = '0%';
      if (DOM.progressTimerText) DOM.progressTimerText.textContent = 'Manual Mode';
      return;
    }

    const duration = durationSec * 1000;
    STATE.currentSlideDuration = duration;
    STATE.slideStartTime = performance.now();

    function updateProgress(now) {
      if (STATE.isPaused || STATE.isPausedForHidden) return;
      if (STATE.schedulerStrategy === 'manual') {
        if (DOM.slideProgress) DOM.slideProgress.style.width = '0%';
        if (DOM.progressTimerText) DOM.progressTimerText.textContent = 'Manual Mode';
        return;
      }

      const elapsed = now - STATE.slideStartTime;
      const pct = Math.min((elapsed / duration) * 100, 100);
      if (DOM.slideProgress) DOM.slideProgress.style.width = `${pct}%`;

      if (DOM.progressTimerText) {
        const remainingSec = Math.max(0, Math.ceil((duration - elapsed) / 1000));
        const elapsedSec = Math.floor(elapsed / 1000);
        const totalSec = Math.round(duration / 1000);
        const formatTime = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
        DOM.progressTimerText.textContent = `${remainingSec}s (${formatTime(elapsedSec)} / ${formatTime(totalSec)})`;
      }

      if (elapsed < duration) {
        STATE.progressRaf = requestAnimationFrame(updateProgress);
      } else {
        if (DOM.slideProgress) DOM.slideProgress.style.width = '0%';
        if (!STATE.isTransitioning) {
          displayNextWallpaper();
        }
      }
    }

    STATE.progressRaf = requestAnimationFrame(updateProgress);
  }

  function resumeSlideTimerFromVisibility() {
    if (STATE.isPaused || STATE.schedulerStrategy === 'manual') return;
    STATE.isPausedForHidden = false;
    const elapsedSoFar = STATE.savedElapsed || 0;
    const duration = STATE.currentSlideDuration || (STATE.intervalSeconds * 1000);
    STATE.slideStartTime = performance.now() - elapsedSoFar;

    function updateProgress(now) {
      if (STATE.isPaused || STATE.isPausedForHidden) return;
      if (STATE.schedulerStrategy === 'manual') return;
      const elapsed = now - STATE.slideStartTime;
      const pct = Math.min((elapsed / duration) * 100, 100);
      if (DOM.slideProgress) DOM.slideProgress.style.width = `${pct}%`;

      if (DOM.progressTimerText) {
        const remainingSec = Math.max(0, Math.ceil((duration - elapsed) / 1000));
        const elapsedSec = Math.floor(elapsed / 1000);
        const totalSec = Math.round(duration / 1000);
        const formatTime = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
        DOM.progressTimerText.textContent = `${remainingSec}s (${formatTime(elapsedSec)} / ${formatTime(totalSec)})`;
      }

      if (elapsed < duration) {
        STATE.progressRaf = requestAnimationFrame(updateProgress);
      } else {
        if (DOM.slideProgress) DOM.slideProgress.style.width = '0%';
        if (!STATE.isTransitioning) {
          displayNextWallpaper();
        }
      }
    }

    STATE.progressRaf = requestAnimationFrame(updateProgress);
  }

  function togglePlayPause() {
    STATE.isPaused = !STATE.isPaused;
    DOM.iconPause.classList.toggle('hidden', STATE.isPaused);
    DOM.iconPlay.classList.toggle('hidden', !STATE.isPaused);

    if (STATE.isPaused) {
      cancelAnimationFrame(STATE.progressRaf);
      clearTimeout(STATE.timer);
      if (DOM.progressTimerText) {
        const rem = Math.max(0, Math.ceil((STATE.currentSlideDuration - (performance.now() - (STATE.slideStartTime || performance.now()))) / 1000));
        DOM.progressTimerText.textContent = `Paused · ${rem}s left`;
      }
      showToast('Screensaver Paused');
    } else {
      showToast('Screensaver Resumed');
      startSlideTimer();
    }
  }

  // --- AMBIENT PARTICLES (CANVAS HIGH-DPI SCALED) ---
  let particleRaf = null;
  function setupParticles() {
    const canvas = DOM.ambientCanvas;
    const ctx = canvas.getContext('2d');
    let width, height;
    let particles = [];

    function resize() {
      const dpr = window.devicePixelRatio || 1;
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.scale(dpr, dpr);
    }
    window.addEventListener('resize', resize);
    resize();

    const COUNT = 28;
    for (let i = 0; i < COUNT; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        radius: Math.random() * 1.1 + 0.4,
        alpha: Math.random() * 0.35 + 0.1,
        dx: (Math.random() - 0.5) * 0.2,
        dy: -Math.random() * 0.3 - 0.08,
        color: Math.random() > 0.5 ? 'rgba(220, 230, 255,' : 'rgba(180, 205, 245,'
      });
    }

    function render() {
      if (!STATE.particlesEnabled || isReducedMotionActive() || STATE.effectiveQualityProfile === 'low') {
        ctx.clearRect(0, 0, width, height);
        return; // Halt RAF loop when disabled, reduced-motion, or in low resource mode
      }

      ctx.clearRect(0, 0, width, height);
      const renderCount = STATE.effectiveQualityProfile === 'balanced' ? Math.floor(particles.length / 2) : particles.length;
      for (let idx = 0; idx < renderCount; idx++) {
        const p = particles[idx];
        p.x += p.dx;
        p.y += p.dy;
        if (p.y < 0) p.y = height + 5;
        if (p.x < 0) p.x = width;
        if (p.x > width) p.x = 0;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = `${p.color} ${p.alpha})`;
        ctx.shadowBlur = 4;
        ctx.shadowColor = p.color + ' 0.5)';
        ctx.fill();
      }
      particleRaf = requestAnimationFrame(render);
    }

    window.toggleParticleLoop = function (enabled) {
      cancelAnimationFrame(particleRaf);
      if (enabled) particleRaf = requestAnimationFrame(render);
      else ctx.clearRect(0, 0, width, height);
    };

    if (STATE.particlesEnabled) {
      particleRaf = requestAnimationFrame(render);
    }
  }

  // --- IDLE HUD AUTO-HIDE (Inactivity Auto-Dimmer) ---
  function startIdleDetector() {
    function resetIdle() {
      document.body.classList.remove('idle-dimmed');
      clearTimeout(STATE.idleTimer);
      if (STATE.oledEnabled && !STATE.oledAutoDim) return;
      STATE.idleTimer = setTimeout(() => {
        if (!DOM.settingsModal.classList.contains('hidden') || !DOM.exhaustionOverlay.classList.contains('hidden')) return;
        document.body.classList.add('idle-dimmed');
      }, 3500);
    }

    window.addEventListener('mousemove', resetIdle, { passive: true });
    window.addEventListener('mousedown', resetIdle, { passive: true });
    window.addEventListener('keydown', resetIdle, { passive: true });
    window.addEventListener('touchstart', resetIdle, { passive: true });
    resetIdle();
  }

  // --- OLED CARE & BURN-IN PREVENTION ENGINE ---
  let oledRepositionTimer = null;
  let oledWpDriftTimer = null;
  let oledDriftStep = 0;

  function repositionHudAndWidgets() {
    if (!STATE.oledEnabled || !STATE.oledHudShift) {
      document.documentElement.style.setProperty('--oled-shift-x', '0px');
      document.documentElement.style.setProperty('--oled-shift-y', '0px');
      document.documentElement.style.setProperty('--oled-widget-shift-x', '0px');
      document.documentElement.style.setProperty('--oled-widget-shift-y', '0px');
      return;
    }

    // Generate subtle random micro-shifts within safe boundary limits
    // HUD Zone shift: [-16px, +16px] horizontal, [-10px, +10px] vertical
    const shiftX = Math.round((Math.random() * 32) - 16);
    const shiftY = Math.round((Math.random() * 20) - 10);

    // Widget micro-shift: [-5px, +5px] horizontal, [-4px, +4px] vertical
    const widgetX = Math.round((Math.random() * 10) - 5);
    const widgetY = Math.round((Math.random() * 8) - 4);

    document.documentElement.style.setProperty('--oled-shift-x', `${shiftX}px`);
    document.documentElement.style.setProperty('--oled-shift-y', `${shiftY}px`);
    document.documentElement.style.setProperty('--oled-widget-shift-x', `${widgetX}px`);
    document.documentElement.style.setProperty('--oled-widget-shift-y', `${widgetY}px`);
  }

  function startOledRepositionLoop() {
    clearInterval(oledRepositionTimer);
    repositionHudAndWidgets();
    // Shift every 12 minutes within safe boundaries
    oledRepositionTimer = setInterval(repositionHudAndWidgets, 12 * 60 * 1000);
  }

  function updateWallpaperPixelShift() {
    if (!STATE.oledEnabled || !STATE.oledWpShift) {
      document.documentElement.style.setProperty('--oled-wp-shift-x', '0px');
      document.documentElement.style.setProperty('--oled-wp-shift-y', '0px');
      return;
    }

    // Lissajous organic micro-drift across 60-second steps
    oledDriftStep = (oledDriftStep + 1) % 12;
    const angle = (oledDriftStep / 12) * Math.PI * 2;
    const driftX = Math.round(Math.sin(angle) * 7);
    const driftY = Math.round(Math.cos(angle * 2) * 5);

    document.documentElement.style.setProperty('--oled-wp-shift-x', `${driftX}px`);
    document.documentElement.style.setProperty('--oled-wp-shift-y', `${driftY}px`);
  }

  function startWallpaperDriftLoop() {
    clearInterval(oledWpDriftTimer);
    updateWallpaperPixelShift();
    oledWpDriftTimer = setInterval(updateWallpaperPixelShift, 45 * 1000);
  }

  function evaluateNightMode() {
    if (!STATE.oledEnabled) {
      document.body.classList.remove('oled-night-mode');
      return;
    }

    if (STATE.oledNightMode === 'always') {
      document.body.classList.add('oled-night-mode');
    } else if (STATE.oledNightMode === 'off') {
      document.body.classList.remove('oled-night-mode');
    } else if (STATE.oledNightMode === 'auto') {
      const h = new Date().getHours();
      const isNight = (h >= 21 || h < 7);
      document.body.classList.toggle('oled-night-mode', isNight);
    }
  }

  function applyOledPreferences() {
    const isOled = STATE.oledEnabled;

    if (DOM.oledSubcontrols) {
      DOM.oledSubcontrols.classList.toggle('disabled', !isOled);
    }

    // Base & Dimmed HUD opacities
    const baseOpacity = isOled ? (STATE.hudBaseOpacity / 100) : 1;
    const dimmedOpacity = (isOled && STATE.oledAutoDim) ? (STATE.oledIdleOpacity / 100) : baseOpacity;
    const scrimOpacity = isOled ? (STATE.oledScrim / 100) : 0;

    document.documentElement.style.setProperty('--hud-base-opacity', String(baseOpacity));
    document.documentElement.style.setProperty('--hud-dimmed-opacity', String(dimmedOpacity));
    document.documentElement.style.setProperty('--oled-scrim-opacity', String(scrimOpacity));

    // Soft White mode
    document.body.classList.toggle('oled-soft-white', isOled && STATE.oledSoftWhite);

    // Night Mode
    evaluateNightMode();

    // Start or adjust loops
    startOledRepositionLoop();
    startWallpaperDriftLoop();
  }

  // --- DISPLAY MODES SPECIFICATION ---
  function setDisplayMode(mode) {
    if (!['ambient', 'cinematic', 'dashboard'].includes(mode)) mode = 'ambient';
    STATE.displayMode = mode;
    localStorage.setItem('kuro_display_mode', mode);

    document.body.classList.remove('display-mode-ambient', 'display-mode-cinematic', 'display-mode-dashboard');
    document.body.classList.add(`display-mode-${mode}`);

    DOM.modePills.forEach(p => {
      p.classList.toggle('active', p.dataset.mode === mode);
    });

    if (DOM.settingDisplayMode) {
      DOM.settingDisplayMode.value = mode;
    }

    const modeLabels = {
      ambient: 'Ambient Mode (Minimal auto-dimming HUD)',
      cinematic: 'Cinematic Mode (Full-screen pure artwork)',
      dashboard: 'Dashboard Mode (Expanded statistics & clock)'
    };
    showToast(modeLabels[mode] || `Display Mode: ${mode}`);

    if (mode === 'cinematic' && DOM.hudBottomLeft) {
      DOM.hudBottomLeft.classList.add('cinematic-reveal');
      clearTimeout(STATE.cinematicRevealTimer);
      STATE.cinematicRevealTimer = setTimeout(() => {
        DOM.hudBottomLeft.classList.remove('cinematic-reveal');
      }, 4500);
    }
  }

  function cycleDisplayMode() {
    const modes = ['ambient', 'cinematic', 'dashboard'];
    const currentIdx = modes.indexOf(STATE.displayMode);
    const nextMode = modes[(currentIdx + 1) % modes.length];
    setDisplayMode(nextMode);
  }

  // --- FAVORITING ---
  function toggleFavorite() {
    if (!STATE.currentWallpaper) return;
    const wp = STATE.currentWallpaper;
    const idx = STATE.favorites.findIndex(f => f.id === wp.id);

    if (idx >= 0) {
      STATE.favorites.splice(idx, 1);
      showToast('Removed from favorites');
      DOM.btnFavorite.classList.remove('favorited');
      if (DOM.favLabel) DOM.favLabel.textContent = 'Favorite';
      backendPost('/api/favorite/remove', { id: wp.id }).catch(() => {});
    } else {
      STATE.favorites.push(wp);
      showToast('Artwork saved to favorites! ❤️');
      DOM.btnFavorite.classList.add('favorited');
      if (DOM.favLabel) DOM.favLabel.textContent = 'Favorited';

      backendPost('/api/favorite', {
        id: wp.id,
        url: wp.url,
        resolution: wp.resolution || '',
        anime: wp.anime || '',
        character: wp.character || '',
        source: wp.source || 'Wallhaven'
      }).catch(() => {});
    }

    localStorage.setItem('kuro_favorites', JSON.stringify(STATE.favorites));
    if (DOM.statFavoritesCount) DOM.statFavoritesCount.textContent = STATE.favorites.length;
    if (DOM.statLibFavorites) DOM.statLibFavorites.textContent = STATE.favorites.length;
    if (DOM.dashStatFavs) DOM.dashStatFavs.textContent = STATE.favorites.length;
  }

  // --- NOTIFICATION TOAST ---
  let toastTimer = null;
  function showToast(msg) {
    DOM.toast.textContent = msg;
    DOM.toast.classList.remove('hidden');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      DOM.toast.classList.add('hidden');
    }, 2800);
  }

  // =========================================================================
  // ADVANCED ANIME AMBIENT CONTROL CENTER CONTROLLER
  // =========================================================================
  let activeControlTab = 'general';
  let savedVisualState = null;

  function captureVisualState() {
    return {
      theme: localStorage.getItem('kuro_theme') || 'kuro-dark',
      dynamicAccent: localStorage.getItem('kuro_dynamic_accent') !== 'false',
      accentColor: localStorage.getItem('kuro_accent_color') || '#38bdf8',
      transitionStyle: STATE.transitionStyle || 'random',
      transitionDuration: STATE.transitionDuration || 2.5,
      motionStyle: STATE.motionStyle || 'random',
      motionIntensity: localStorage.getItem('kuro_motion_intensity') || 'normal',
      reducedMotion: STATE.reducedMotion || false,
      particlesEnabled: STATE.particlesEnabled !== false,
      particleDensity: localStorage.getItem('kuro_particle_density') || 'medium',
      particleSpeed: localStorage.getItem('kuro_particle_speed') || 'normal',
      hudBaseOpacity: STATE.hudBaseOpacity !== undefined ? STATE.hudBaseOpacity : 100,
      oledIdleOpacity: STATE.oledIdleOpacity !== undefined ? STATE.oledIdleOpacity : 15,
      oledScrim: STATE.oledScrim !== undefined ? STATE.oledScrim : 0,
      oledNightMode: STATE.oledNightMode || 'off',
      uiScale: localStorage.getItem('kuro_ui_scale') || '100%',
      wpFitMode: localStorage.getItem('kuro_wp_fit_mode') || 'fill',
      compBlurEnabled: STATE.compositionSettings ? STATE.compositionSettings.blurred_backdrop_enabled !== false : true,
      compBlurIntensity: STATE.compositionSettings ? (STATE.compositionSettings.blur_intensity_px || 28) : 28
    };
  }

  function applyVisualPreview(state) {
    if (!state) return;
    document.documentElement.dataset.theme = state.theme || 'kuro-dark';

    const effectiveAccent = state.dynamicAccent ? (STATE.extractedAccent || state.accentColor || '#38bdf8') : (state.accentColor || '#38bdf8');
    document.documentElement.style.setProperty('--dynamic-accent', effectiveAccent);
    document.documentElement.style.setProperty('--dynamic-accent-glow', `${effectiveAccent}44`);

    const baseOp = (state.hudBaseOpacity / 100).toString();
    const idleOp = (state.oledIdleOpacity / 100).toString();
    document.documentElement.style.setProperty('--hud-base-opacity', baseOp);
    document.documentElement.style.setProperty('--hud-dimmed-opacity', idleOp);

    document.documentElement.style.setProperty('--transition-duration', `${state.transitionDuration}s`);
    document.documentElement.style.setProperty('--oled-scrim-opacity', (state.oledScrim / 100).toString());
    document.documentElement.style.setProperty('--wp-blur-radius', `${state.compBlurIntensity}px`);

    if (state.uiScale && state.uiScale !== '100%') {
      document.body.style.zoom = state.uiScale;
    } else {
      document.body.style.zoom = '';
    }

    if (window.toggleParticleLoop) {
      window.toggleParticleLoop(state.particlesEnabled && !state.reducedMotion);
    }
  }

  function triggerVisualPreview() {
    const current = {
      theme: DOM.settingVisualTheme ? DOM.settingVisualTheme.value : 'kuro-dark',
      dynamicAccent: DOM.settingVisualDynamicAccent ? DOM.settingVisualDynamicAccent.checked : true,
      accentColor: DOM.settingVisualAccentColor ? DOM.settingVisualAccentColor.value : '#38bdf8',
      transitionStyle: DOM.settingTransition ? DOM.settingTransition.value : 'random',
      transitionDuration: DOM.settingTransitionDuration ? parseFloat(DOM.settingTransitionDuration.value) : 2.5,
      motionStyle: DOM.settingMotion ? DOM.settingMotion.value : 'random',
      motionIntensity: DOM.settingMotionIntensity ? DOM.settingMotionIntensity.value : 'normal',
      reducedMotion: DOM.settingReducedMotion ? DOM.settingReducedMotion.checked : false,
      particlesEnabled: DOM.settingParticles ? DOM.settingParticles.checked : true,
      particleDensity: DOM.settingParticleDensity ? DOM.settingParticleDensity.value : 'medium',
      particleSpeed: DOM.settingParticleSpeed ? DOM.settingParticleSpeed.value : 'normal',
      hudBaseOpacity: DOM.settingHudBaseOpacity ? parseInt(DOM.settingHudBaseOpacity.value, 10) : 100,
      oledIdleOpacity: DOM.settingOledIdleOpacity ? parseInt(DOM.settingOledIdleOpacity.value, 10) : 15,
      oledScrim: DOM.settingOledScrim ? parseInt(DOM.settingOledScrim.value, 10) : 0,
      oledNightMode: DOM.settingOledNightMode ? DOM.settingOledNightMode.value : 'off',
      uiScale: DOM.settingUiScale ? DOM.settingUiScale.value : '100%',
      wpFitMode: DOM.settingWpFitMode ? DOM.settingWpFitMode.value : 'fill',
      compBlurEnabled: DOM.settingCompBlurEnabled ? DOM.settingCompBlurEnabled.checked : true,
      compBlurIntensity: DOM.settingCompBlurIntensity ? parseInt(DOM.settingCompBlurIntensity.value, 10) : 28
    };

    applyVisualPreview(current);
    if (DOM.settingsChangesBadge) {
      DOM.settingsChangesBadge.classList.remove('hidden');
    }
    validateControlCenter();
  }

  function openControlCenter() {
    savedVisualState = captureVisualState();
    DOM.settingsModal.classList.remove('hidden');

    if (DOM.settingVisualTheme) DOM.settingVisualTheme.value = savedVisualState.theme;
    if (DOM.settingVisualDynamicAccent) DOM.settingVisualDynamicAccent.checked = savedVisualState.dynamicAccent;
    if (DOM.settingVisualAccentColor) DOM.settingVisualAccentColor.value = savedVisualState.accentColor;
    if (DOM.settingMotionIntensity) DOM.settingMotionIntensity.value = savedVisualState.motionIntensity;
    if (DOM.settingParticleDensity) DOM.settingParticleDensity.value = savedVisualState.particleDensity;
    if (DOM.settingParticleSpeed) DOM.settingParticleSpeed.value = savedVisualState.particleSpeed;
    if (DOM.settingUiScale) DOM.settingUiScale.value = savedVisualState.uiScale;
    if (DOM.settingWpFitMode) DOM.settingWpFitMode.value = savedVisualState.wpFitMode;
    if (DOM.settingCompBlurEnabled) DOM.settingCompBlurEnabled.checked = savedVisualState.compBlurEnabled;
    if (DOM.settingCompBlurIntensity) {
      DOM.settingCompBlurIntensity.value = savedVisualState.compBlurIntensity;
      if (DOM.settingCompBlurLabel) DOM.settingCompBlurLabel.textContent = `${savedVisualState.compBlurIntensity}px`;
    }

    if (DOM.settingMinResolution) DOM.settingMinResolution.value = localStorage.getItem('kuro_min_resolution') || 'any';
    if (DOM.settingDuplicateSensitivity) DOM.settingDuplicateSensitivity.value = localStorage.getItem('kuro_duplicate_sensitivity') || 'strict';
    if (DOM.settingPerfPrefetch) {
      const q = parseInt(localStorage.getItem('kuro_prefetch_size') || '6', 10);
      DOM.settingPerfPrefetch.value = q;
      if (DOM.settingPerfPrefetchLabel) DOM.settingPerfPrefetchLabel.textContent = `${q} slides`;
    }
    if (DOM.settingPerfCacheLimit) {
      const cl = parseInt(localStorage.getItem('kuro_cache_limit') || '2048', 10);
      DOM.settingPerfCacheLimit.value = cl;
      if (DOM.settingPerfCacheLimitLabel) DOM.settingPerfCacheLimitLabel.textContent = `${cl} MB (${(cl/1024).toFixed(1)} GB)`;
    }
    if (DOM.settingPerfWorkers) DOM.settingPerfWorkers.value = localStorage.getItem('kuro_workers') || '2';
    if (DOM.settingPerfDownloadLimit) DOM.settingPerfDownloadLimit.value = localStorage.getItem('kuro_download_limit') || '2';
    if (DOM.settingPerfAnimQuality) DOM.settingPerfAnimQuality.value = localStorage.getItem('kuro_anim_quality') || '60fps';

    if (DOM.settingsSearchInput) {
      DOM.settingsSearchInput.value = '';
      filterControlCenterSearch('');
    }
    switchControlCenterTab(activeControlTab || 'general');

    if (DOM.swatches) {
      DOM.swatches.forEach(s => {
        s.classList.toggle('active', s.dataset.color.toLowerCase() === savedVisualState.accentColor.toLowerCase());
      });
    }

    if (DOM.settingsChangesBadge) DOM.settingsChangesBadge.classList.add('hidden');
    validateControlCenter();

    loadPersonalizationProfile();
    loadQualitySettings();
    loadSchedulerSettings();
    loadSoundscapeSettings();
    loadControlCenterFromBackend();
    loadProviderSettings();
    fetchDatabaseIntegrity();
    fetchBackupsList();
  }

  function closeControlCenter(revert = false) {
    if (revert && savedVisualState) {
      applyVisualPreview(savedVisualState);
      showToast('Unsaved preview discarded');
    }
    DOM.settingsModal.classList.add('hidden');
    if (DOM.settingsChangesBadge) DOM.settingsChangesBadge.classList.add('hidden');
  }

  function switchControlCenterTab(tabName) {
    activeControlTab = tabName;
    if (DOM.navTabs) {
      DOM.navTabs.forEach(t => {
        const isCurrent = t.dataset.tab === tabName;
        t.classList.toggle('active', isCurrent);
        t.setAttribute('aria-selected', isCurrent ? 'true' : 'false');
      });
    }

    if (DOM.controlSections) {
      DOM.controlSections.forEach(sec => {
        const matches = sec.dataset.section === tabName;
        sec.classList.toggle('hidden', !matches);
        if (matches) sec.classList.remove('search-hidden');
      });
    }

    const meta = {
      general: { title: '⚙️ General Preferences', desc: 'Default display modes, slideshow timing strategies, clock and weather.' },
      wallpaper: { title: '🖼️ Wallpaper & Discovery', desc: 'Franchise selection, character filters, weights, resolution & quality thresholds.' },
      visual: { title: '🎨 Visual Style & Ambiance', desc: 'Color themes, palette accents, transition kinetics, particles & OLED protection.' },
      display: { title: '🖥️ Display & Monitor Topology', desc: 'Target Windows monitor, aspect orientation, scaling factors & focal composition.' },
      performance: { title: '⚡ Performance & Caching', desc: 'Prefetch buffer, disk cache limits, background worker threads & graphics fidelity.' },
      privacy: { title: '🔒 Privacy, Backup & Reset', desc: 'Local SQLite WAL history, taste learning profile, JSON config export & factory reset.' },
      moderation: { title: '🛡️ Content Safety & Moderation', desc: 'Strict SFW policy, custom blocklists (tags, characters, artists, franchises) & review queue.' }
    }[tabName];

    if (meta) {
      if (DOM.activeSectionTitle) DOM.activeSectionTitle.textContent = meta.title;
      if (DOM.activeSectionDesc) DOM.activeSectionDesc.textContent = meta.desc;
    }

    if (tabName === 'privacy') {
      fetchDatabaseIntegrity();
      fetchBackupsList();
    } else if (tabName === 'moderation') {
      fetchModerationSettings();
      fetchBlockedEntities();
      fetchReviewQueue();
    }
  }

  function filterControlCenterSearch(query) {
    const q = (query || '').trim().toLowerCase();
    const hasQuery = q.length > 0;
    if (DOM.btnSettingsSearchClear) {
      DOM.btnSettingsSearchClear.classList.toggle('hidden', !hasQuery);
    }

    const sectionCounts = { general: 0, wallpaper: 0, visual: 0, display: 0, performance: 0, privacy: 0, moderation: 0 };

    if (!hasQuery) {
      if (DOM.controlSections) {
        DOM.controlSections.forEach(sec => {
          sec.classList.toggle('hidden', sec.dataset.section !== activeControlTab);
          const cards = sec.querySelectorAll('.setting-card, .setting-group');
          cards.forEach(c => c.classList.remove('search-hidden'));
        });
      }
      if (DOM.navTabs) {
        DOM.navTabs.forEach(t => {
          const badge = t.querySelector('.nav-badge');
          if (badge) { badge.style.display = 'none'; badge.textContent = ''; }
        });
      }
      return;
    }

    if (DOM.controlSections) {
      DOM.controlSections.forEach(sec => {
        const secName = sec.dataset.section;
        let count = 0;
        const cards = sec.querySelectorAll('.setting-card, .setting-group');
        cards.forEach(card => {
          const text = (card.textContent || '').toLowerCase();
          const match = text.includes(q);
          card.classList.toggle('search-hidden', !match);
          if (match) count++;
        });
        sectionCounts[secName] = count;
        sec.classList.toggle('hidden', count === 0);
      });
    }

    if (DOM.navTabs) {
      DOM.navTabs.forEach(t => {
        const secName = t.dataset.tab;
        const count = sectionCounts[secName] || 0;
        const badge = t.querySelector('.nav-badge');
        if (badge) {
          if (count > 0) {
            badge.style.display = 'inline-block';
            badge.textContent = count;
          } else {
            badge.style.display = 'none';
          }
        }
      });
    }
  }

  function validateControlCenter() {
    let isValid = true;
    let message = '✓ All settings valid';

    if (DOM.settingInterval) {
      const v = parseInt(DOM.settingInterval.value, 10);
      if (isNaN(v) || v < 5 || v > 600) {
        isValid = false;
        message = '⚠️ Slide interval must be between 5s and 600s';
      }
    }

    if (DOM.settingRandomMin && DOM.settingRandomMax) {
      const min = parseInt(DOM.settingRandomMin.value, 10);
      const max = parseInt(DOM.settingRandomMax.value, 10);
      if (min > max) {
        isValid = false;
        message = '⚠️ Random min interval cannot exceed max interval';
      }
    }

    if (DOM.settingPerfPrefetch) {
      const pq = parseInt(DOM.settingPerfPrefetch.value, 10);
      if (isNaN(pq) || pq < 2 || pq > 30) {
        isValid = false;
        message = '⚠️ Prefetch queue must be between 2 and 30';
      }
    }

    if (DOM.settingPerfCacheLimit) {
      const cl = parseInt(DOM.settingPerfCacheLimit.value, 10);
      if (isNaN(cl) || cl < 200 || cl > 20000) {
        isValid = false;
        message = '⚠️ Cache limit must be between 200MB and 20000MB';
      }
    }

    if (DOM.settingsValidationBadge) {
      DOM.settingsValidationBadge.className = `validation-badge ${isValid ? 'valid' : 'invalid'}`;
      DOM.settingsValidationBadge.textContent = message;
    }
    return isValid;
  }

  function resetActiveSection() {
    const sec = activeControlTab || 'general';
    const defaults = {
      general: () => {
        if (DOM.settingDisplayMode) DOM.settingDisplayMode.value = 'ambient';
        if (DOM.settingInterval) { DOM.settingInterval.value = 30; if (DOM.settingIntervalLabel) DOM.settingIntervalLabel.textContent = '30s'; }
        if (DOM.settingScheduleStrategy) DOM.settingScheduleStrategy.value = 'fixed';
        if (DOM.settingLaunchMode) DOM.settingLaunchMode.value = 'kiosk';
        if (DOM.settingWinStartup) DOM.settingWinStartup.checked = false;
        const timeRadios = document.querySelectorAll('input[name="timeFormat"]');
        timeRadios.forEach(r => r.checked = r.value === '12');
        if (DOM.settingShowSeconds) DOM.settingShowSeconds.checked = true;
        if (DOM.settingDateFormat) DOM.settingDateFormat.value = 'full';
        if (DOM.settingSecondTz) DOM.settingSecondTz.value = 'none';
        const tempRadios = document.querySelectorAll('input[name="tempUnit"]');
        tempRadios.forEach(r => r.checked = r.value === 'C');
        if (DOM.settingCity) DOM.settingCity.value = '';
      },
      wallpaper: () => {
        if (DOM.settingAnime) DOM.settingAnime.value = 'all';
        if (DOM.settingCharacter) DOM.settingCharacter.value = 'all';
        if (DOM.settingMinResolution) DOM.settingMinResolution.value = 'any';
        if (DOM.settingQualityThreshold) { DOM.settingQualityThreshold.value = 50; if (DOM.settingQualityThresholdLabel) DOM.settingQualityThresholdLabel.textContent = '50 / 100'; }
        if (DOM.settingQualityPopWeight) DOM.settingQualityPopWeight.value = '0.35';
        if (DOM.settingRatio) DOM.settingRatio.value = 'auto';
        if (DOM.settingQualityNativeRes) DOM.settingQualityNativeRes.checked = true;
        if (DOM.settingQualityAspectRatio) DOM.settingQualityAspectRatio.checked = true;
        if (DOM.settingQualityAvoidBright) DOM.settingQualityAvoidBright.checked = true;
        if (DOM.settingQualityAvoidDark) DOM.settingQualityAvoidDark.checked = false;
        if (DOM.settingDuplicateSensitivity) DOM.settingDuplicateSensitivity.value = 'strict';
        if (DOM.settingRecDiversity) DOM.settingRecDiversity.checked = true;
      },
      visual: () => {
        if (DOM.settingVisualTheme) DOM.settingVisualTheme.value = 'kuro-dark';
        if (DOM.settingVisualDynamicAccent) DOM.settingVisualDynamicAccent.checked = true;
        if (DOM.settingVisualAccentColor) DOM.settingVisualAccentColor.value = '#38bdf8';
        if (DOM.settingTransition) DOM.settingTransition.value = 'random';
        if (DOM.settingTransitionDuration) DOM.settingTransitionDuration.value = '2.5';
        if (DOM.settingMotion) DOM.settingMotion.value = 'random';
        if (DOM.settingMotionIntensity) DOM.settingMotionIntensity.value = 'normal';
        if (DOM.settingReducedMotion) DOM.settingReducedMotion.checked = false;
        if (DOM.settingParticles) DOM.settingParticles.checked = true;
        if (DOM.settingParticleDensity) DOM.settingParticleDensity.value = 'medium';
        if (DOM.settingParticleSpeed) DOM.settingParticleSpeed.value = 'normal';
        if (DOM.settingHudBaseOpacity) { DOM.settingHudBaseOpacity.value = 100; if (DOM.settingHudBaseOpacityLabel) DOM.settingHudBaseOpacityLabel.textContent = '100%'; }
        if (DOM.settingOledIdleOpacity) { DOM.settingOledIdleOpacity.value = 15; if (DOM.settingOledIdleOpacityLabel) DOM.settingOledIdleOpacityLabel.textContent = '15%'; }
        if (DOM.settingOledScrim) { DOM.settingOledScrim.value = 0; if (DOM.settingOledScrimLabel) DOM.settingOledScrimLabel.textContent = '0%'; }
        if (DOM.settingOledNightMode) DOM.settingOledNightMode.value = 'off';
        if (DOM.settingOledAutoDim) DOM.settingOledAutoDim.checked = true;
        if (DOM.settingOledHudShift) DOM.settingOledHudShift.checked = true;
        if (DOM.settingOledWpShift) DOM.settingOledWpShift.checked = true;
        if (DOM.settingOledSoftWhite) DOM.settingOledSoftWhite.checked = true;
        triggerVisualPreview();
      },
      display: () => {
        if (DOM.settingMonitor) DOM.settingMonitor.value = 'auto';
        if (DOM.settingDisplayOrientation) DOM.settingDisplayOrientation.value = 'auto';
        if (DOM.settingWinScaling) DOM.settingWinScaling.checked = true;
        if (DOM.settingUiScale) DOM.settingUiScale.value = '100%';
        if (DOM.settingWpFitMode) DOM.settingWpFitMode.value = 'fill';
        if (DOM.settingFocalPoint) DOM.settingFocalPoint.value = 'auto';
        if (DOM.settingCompBlurEnabled) DOM.settingCompBlurEnabled.checked = true;
        if (DOM.settingCompBlurIntensity) { DOM.settingCompBlurIntensity.value = 28; if (DOM.settingCompBlurLabel) DOM.settingCompBlurLabel.textContent = '28px'; }
        triggerVisualPreview();
      },
      performance: () => {
        if (DOM.settingPerfPrefetch) { DOM.settingPerfPrefetch.value = 6; if (DOM.settingPerfPrefetchLabel) DOM.settingPerfPrefetchLabel.textContent = '6 slides'; }
        if (DOM.settingPerfCacheLimit) { DOM.settingPerfCacheLimit.value = 2048; if (DOM.settingPerfCacheLimitLabel) DOM.settingPerfCacheLimitLabel.textContent = '2048 MB (2.0 GB)'; }
        if (DOM.settingPerfWorkers) DOM.settingPerfWorkers.value = '2';
        if (DOM.settingPerfDownloadLimit) DOM.settingPerfDownloadLimit.value = '2';
        if (DOM.settingPerfAnimQuality) DOM.settingPerfAnimQuality.value = '60fps';
      },
      privacy: () => {
        if (DOM.settingRecEnabled) DOM.settingRecEnabled.checked = true;
      }
    }[sec];

    if (defaults) defaults();
    if (DOM.settingsChangesBadge) DOM.settingsChangesBadge.classList.remove('hidden');
    validateControlCenter();
    showToast(`Reset ${sec} preferences to defaults`);
  }

  async function saveControlCenterChanges() {
    if (!validateControlCenter()) {
      showToast('⚠️ Please fix settings validation errors before saving');
      return;
    }

    if (DOM.settingDisplayMode) {
      STATE.displayMode = DOM.settingDisplayMode.value;
      setDisplayMode(STATE.displayMode);
    }
    if (DOM.settingInterval) {
      STATE.intervalSeconds = parseInt(DOM.settingInterval.value, 10);
      localStorage.setItem('kuro_interval', STATE.intervalSeconds);
    }
    if (DOM.settingScheduleStrategy) {
      STATE.schedulerStrategy = DOM.settingScheduleStrategy.value;
      localStorage.setItem('kuro_scheduler_strategy', STATE.schedulerStrategy);
    }

    if (DOM.settingAnime) {
      STATE.currentAnime = DOM.settingAnime.value;
      localStorage.setItem('kuro_anime', STATE.currentAnime);
    }
    if (DOM.settingMinResolution) {
      localStorage.setItem('kuro_min_resolution', DOM.settingMinResolution.value);
    }
    if (DOM.settingDuplicateSensitivity) {
      localStorage.setItem('kuro_duplicate_sensitivity', DOM.settingDuplicateSensitivity.value);
    }

    if (DOM.settingVisualTheme) {
      STATE.theme = DOM.settingVisualTheme.value;
      localStorage.setItem('kuro_theme', STATE.theme);
    }
    if (DOM.settingVisualDynamicAccent) {
      STATE.dynamicAccent = DOM.settingVisualDynamicAccent.checked;
      localStorage.setItem('kuro_dynamic_accent', STATE.dynamicAccent);
    }
    if (DOM.settingVisualAccentColor) {
      STATE.accentColor = DOM.settingVisualAccentColor.value;
      localStorage.setItem('kuro_accent_color', STATE.accentColor);
    }
    if (DOM.settingTransition) {
      STATE.transitionStyle = DOM.settingTransition.value;
      localStorage.setItem('kuro_transition', STATE.transitionStyle);
    }
    if (DOM.settingTransitionDuration) {
      STATE.transitionDuration = parseFloat(DOM.settingTransitionDuration.value);
      localStorage.setItem('kuro_transition_duration', STATE.transitionDuration);
    }
    if (DOM.settingMotion) {
      STATE.motionStyle = DOM.settingMotion.value;
      localStorage.setItem('kuro_motion', STATE.motionStyle);
    }
    if (DOM.settingMotionIntensity) {
      STATE.motionIntensity = DOM.settingMotionIntensity.value;
      localStorage.setItem('kuro_motion_intensity', STATE.motionIntensity);
    }
    if (DOM.settingReducedMotion) {
      STATE.reducedMotion = DOM.settingReducedMotion.checked;
      localStorage.setItem('kuro_reduced_motion', STATE.reducedMotion);
    }
    if (DOM.settingParticles) {
      STATE.particlesEnabled = DOM.settingParticles.checked;
      localStorage.setItem('kuro_particles', STATE.particlesEnabled);
    }
    if (DOM.settingParticleDensity) {
      STATE.particleDensity = DOM.settingParticleDensity.value;
      localStorage.setItem('kuro_particle_density', STATE.particleDensity);
    }
    if (DOM.settingParticleSpeed) {
      STATE.particleSpeed = DOM.settingParticleSpeed.value;
      localStorage.setItem('kuro_particle_speed', STATE.particleSpeed);
    }
    if (DOM.settingHudBaseOpacity) {
      STATE.hudBaseOpacity = parseInt(DOM.settingHudBaseOpacity.value, 10);
      localStorage.setItem('kuro_hud_base_opacity', STATE.hudBaseOpacity);
    }
    if (DOM.settingOledIdleOpacity) {
      STATE.oledIdleOpacity = parseInt(DOM.settingOledIdleOpacity.value, 10);
      localStorage.setItem('kuro_oled_idle_opacity', STATE.oledIdleOpacity);
    }
    if (DOM.settingOledScrim) {
      STATE.oledScrim = parseInt(DOM.settingOledScrim.value, 10);
      localStorage.setItem('kuro_oled_scrim', STATE.oledScrim);
    }
    if (DOM.settingOledNightMode) {
      STATE.oledNightMode = DOM.settingOledNightMode.value;
      localStorage.setItem('kuro_oled_night_mode', STATE.oledNightMode);
    }

    if (DOM.settingUiScale) {
      STATE.uiScale = DOM.settingUiScale.value;
      localStorage.setItem('kuro_ui_scale', STATE.uiScale);
    }
    if (DOM.settingWpFitMode) {
      localStorage.setItem('kuro_wp_fit_mode', DOM.settingWpFitMode.value);
    }
    if (DOM.settingFocalPoint) {
      STATE.focalPointMode = DOM.settingFocalPoint.value;
      localStorage.setItem('kuro_focal_point', STATE.focalPointMode);
    }

    if (DOM.settingPerfPrefetch) {
      localStorage.setItem('kuro_prefetch_size', DOM.settingPerfPrefetch.value);
    }
    if (DOM.settingPerfCacheLimit) {
      localStorage.setItem('kuro_cache_limit', DOM.settingPerfCacheLimit.value);
    }
    if (DOM.settingPerfWorkers) {
      localStorage.setItem('kuro_workers', DOM.settingPerfWorkers.value);
    }
    if (DOM.settingPerfDownloadLimit) {
      localStorage.setItem('kuro_download_limit', DOM.settingPerfDownloadLimit.value);
    }
    if (DOM.settingPerfAnimQuality) {
      localStorage.setItem('kuro_anim_quality', DOM.settingPerfAnimQuality.value);
    }

    const consolidatedPayload = {
      general: {
        display_mode: STATE.displayMode,
        slideshow_interval: STATE.intervalSeconds,
        scheduler_strategy: STATE.schedulerStrategy
      },
      wallpaper: {
        wallpaper_franchise: STATE.currentAnime,
        wallpaper_min_resolution: localStorage.getItem('kuro_min_resolution') || 'any',
        wallpaper_duplicate_sensitivity: localStorage.getItem('kuro_duplicate_sensitivity') || 'strict'
      },
      visual: {
        visual_theme: STATE.theme,
        visual_dynamic_accent: STATE.dynamicAccent,
        visual_accent_color: STATE.accentColor,
        visual_transition_style: STATE.transitionStyle,
        visual_transition_duration: STATE.transitionDuration,
        visual_motion_style: STATE.motionStyle,
        visual_animation_intensity: STATE.motionIntensity,
        visual_reduced_motion: STATE.reducedMotion,
        visual_particles_enabled: STATE.particlesEnabled,
        visual_particle_density: STATE.particleDensity,
        visual_particle_speed: STATE.particleSpeed,
        visual_hud_opacity: STATE.hudBaseOpacity,
        visual_idle_opacity: STATE.oledIdleOpacity,
        visual_auto_dim_delay: 3.5
      },
      display: {
        display_target_monitor: DOM.settingMonitor ? DOM.settingMonitor.value : 'auto',
        display_orientation: DOM.settingDisplayOrientation ? DOM.settingDisplayOrientation.value : 'auto',
        display_scaling: DOM.settingWinScaling ? DOM.settingWinScaling.checked : true,
        display_ui_scale: STATE.uiScale,
        display_wallpaper_fitting: DOM.settingWpFitMode ? DOM.settingWpFitMode.value : 'fill',
        display_blurred_backdrop: DOM.settingCompBlurEnabled ? DOM.settingCompBlurEnabled.checked : true,
        display_blur_intensity: DOM.settingCompBlurIntensity ? parseInt(DOM.settingCompBlurIntensity.value, 10) : 28
      },
      performance: {
        perf_prefetch_queue_size: DOM.settingPerfPrefetch ? parseInt(DOM.settingPerfPrefetch.value, 10) : 6,
        perf_cache_limit_mb: DOM.settingPerfCacheLimit ? parseInt(DOM.settingPerfCacheLimit.value, 10) : 2048,
        perf_worker_count: DOM.settingPerfWorkers ? parseInt(DOM.settingPerfWorkers.value, 10) : 2,
        perf_download_limit: DOM.settingPerfDownloadLimit ? parseInt(DOM.settingPerfDownloadLimit.value, 10) : 2,
        perf_animation_quality: DOM.settingPerfAnimQuality ? DOM.settingPerfAnimQuality.value : '60fps'
      },
      privacy: {
        privacy_local_history: true,
        privacy_preference_learning: DOM.settingRecEnabled ? DOM.settingRecEnabled.checked : true
      }
    };

    backendPost('/api/settings', consolidatedPayload).catch(() => {});

    updateSchedulerSettingsFromUI();
    updateQualitySettingsFromUI();
    saveSoundscapeSettingsToBackend();

    savedVisualState = captureVisualState();
    if (DOM.settingsChangesBadge) DOM.settingsChangesBadge.classList.add('hidden');
    DOM.settingsModal.classList.add('hidden');
    showToast('Preferences saved successfully ✨');
  }

  async function loadControlCenterFromBackend() {
    try {
      const res = await backendGet('/api/settings');
      if (res && res.settings) {
        const perf = res.settings.performance;
        if (perf && DOM.settingPerfCacheLimit && !localStorage.getItem('kuro_cache_limit')) {
          DOM.settingPerfCacheLimit.value = perf.perf_cache_limit_mb || 2048;
          if (DOM.settingPerfCacheLimitLabel) DOM.settingPerfCacheLimitLabel.textContent = `${DOM.settingPerfCacheLimit.value} MB`;
        }
      }
      const stats = await backendGet('/api/library/stats');
      if (stats && DOM.statCacheUtilization) {
        const mb = stats.cache_size_mb || 0;
        const lim = DOM.settingPerfCacheLimit ? DOM.settingPerfCacheLimit.value : 2048;
        DOM.statCacheUtilization.textContent = `${mb.toFixed(1)} MB / ${lim} MB`;
      }
    } catch (_) {}
  }

  async function exportSettings() {
    try {
      const res = await backendGet('/api/settings/export');
      const data = res.export || res;
      const exportJson = JSON.stringify(data, null, 2);
      const blob = new Blob([exportJson], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `kuro_ambient_settings_${Date.now()}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast('Settings exported successfully 📥');
    } catch (err) {
      showToast('Failed to export settings ⚠️');
    }
  }

  function handleImportSettingsFile(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (event) => {
      try {
        const parsed = JSON.parse(event.target.result);
        const res = await backendPost('/api/settings/import', { config: parsed });
        if (res && res.status === 'imported') {
          showToast('Settings imported successfully! Reloading... 📤');
          setTimeout(() => location.reload(), 1000);
        } else {
          showToast('Failed to import configuration ⚠️');
        }
      } catch (err) {
        showToast('Invalid JSON settings file ⚠️');
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  }

  async function factoryResetSettings() {
    const confirmed = confirm('⚠️ Reset all settings to factory defaults?\n\nYour saved favorites and curated wallpapers will NOT be deleted.');
    if (!confirmed) return;
    try {
      await backendPost('/api/settings/reset', { factory_reset: true });
      const favs = localStorage.getItem('kuro_favorites');
      localStorage.clear();
      if (favs) localStorage.setItem('kuro_favorites', favs);
      showToast('Preferences reset to factory defaults. Reloading...');
      setTimeout(() => location.reload(), 1000);
    } catch (err) {
      showToast('Failed to reset settings ⚠️');
    }
  }

  async function purgeLocalCache() {
    try {
      const res = await backendPost('/api/cache/purge', {});
      showToast(`Cache purged: ${res.freed_mb || '0'} MB freed 🗑️`);
      if (DOM.statCacheUtilization) DOM.statCacheUtilization.textContent = '0 MB / 2048 MB';
    } catch (err) {
      showToast('Failed to purge cache ⚠️');
    }
  }

  // --- DATABASE INTEGRITY & BACKUP / RECOVERY ---
  async function fetchDatabaseIntegrity() {
    try {
      const res = await fetch(`${STATE.backendBase}/api/database/integrity`, { signal: AbortSignal.timeout(3500) });
      if (res.ok) {
        const data = await res.json();
        updateDatabaseIntegrityUI(data);
      }
    } catch (e) {
      console.warn('[Kuro] Failed to query database integrity:', e);
    }
  }

  function updateDatabaseIntegrityUI(data) {
    if (!DOM.dbIntegrityBadge) return;
    const status = data.status || 'healthy';
    DOM.dbIntegrityBadge.className = `db-health-badge ${status}`;
    if (status === 'healthy') {
      DOM.dbIntegrityBadge.textContent = '● Healthy (WAL Mode)';
    } else if (status === 'warning') {
      DOM.dbIntegrityBadge.textContent = '▲ Warning (Inconsistencies)';
    } else {
      DOM.dbIntegrityBadge.textContent = '✕ Corruption Detected';
    }

    if (DOM.dbMetricSchema) DOM.dbMetricSchema.textContent = `v${data.schema_version || 13}`;
    if (DOM.dbMetricTables) DOM.dbMetricTables.textContent = String(data.tables_count || 17);
    if (DOM.dbMetricSize) DOM.dbMetricSize.textContent = data.db_size_formatted || '0 B';
    if (DOM.dbMetricWal) DOM.dbMetricWal.textContent = data.wal_size_formatted || '0 B';
  }

  async function fetchBackupsList() {
    try {
      const res = await fetch(`${STATE.backendBase}/api/backups`, { signal: AbortSignal.timeout(4000) });
      if (res.ok) {
        const data = await res.json();
        if (data.database_integrity) {
          updateDatabaseIntegrityUI(data.database_integrity);
        }
        renderBackupsList(data.backups || []);
      }
    } catch (e) {
      console.warn('[Kuro] Failed to fetch backups:', e);
    }
  }

  function renderBackupsList(backups) {
    if (!DOM.backupListContainer) return;
    DOM.backupListContainer.innerHTML = '';

    if (!backups || backups.length === 0) {
      if (DOM.backupListEmpty) DOM.backupListEmpty.classList.remove('hidden');
      return;
    }
    if (DOM.backupListEmpty) DOM.backupListEmpty.classList.add('hidden');

    backups.forEach(bkp => {
      const card = document.createElement('div');
      card.className = 'backup-item-card';

      const type = bkp.backup_type || 'manual';
      let typeLabel = 'Manual';
      if (type.includes('pre_migration')) typeLabel = 'Pre-Migration';
      else if (type.includes('pre_restore')) typeLabel = 'Pre-Restore';
      else if (type.includes('auto')) typeLabel = 'Auto';

      const typeClass = type.replace(/-/g, '_');
      const dateStr = bkp.created_at ? new Date(bkp.created_at).toLocaleString() : 'Unknown date';
      const sizeStr = bkp.file_size_formatted || `${Math.round((bkp.file_size || 0)/1024)} KB`;
      const schemaVer = bkp.schema_version ? `v${bkp.schema_version}` : 'v13';

      card.innerHTML = `
        <div class="backup-item-info">
          <div class="backup-item-title" title="${escapeHtml(bkp.filename)}">
            <span class="backup-type-badge ${typeClass}">${typeLabel}</span>
            <span>${escapeHtml(bkp.filename)}</span>
          </div>
          <div class="backup-item-meta">
            <span>📅 ${dateStr}</span>
            <span>💾 ${sizeStr}</span>
            <span>🏷️ ${schemaVer}</span>
          </div>
        </div>
        <div class="backup-item-actions">
          <button class="backup-btn-sm download-btn" data-file="${escapeHtml(bkp.filename)}" title="Download archive (.zip)">⬇️ Download</button>
          <button class="backup-btn-sm restore restore-btn" data-file="${escapeHtml(bkp.filename)}" title="Restore database from this backup">🔄 Restore</button>
          <button class="backup-btn-sm delete delete-btn" data-file="${escapeHtml(bkp.filename)}" title="Delete backup archive">🗑️</button>
        </div>
      `;

      // Download
      card.querySelector('.download-btn').addEventListener('click', () => {
        window.location.href = `${STATE.backendBase}/api/backups/download?filename=${encodeURIComponent(bkp.filename)}`;
      });

      // Restore
      card.querySelector('.restore-btn').addEventListener('click', () => {
        openRestoreModal(bkp.filename);
      });

      // Delete
      card.querySelector('.delete-btn').addEventListener('click', async () => {
        if (!confirm(`Delete backup archive ${bkp.filename}?`)) return;
        try {
          const token = localStorage.getItem('kuro_token') || '';
          const dRes = await fetch(`${STATE.backendBase}/api/backups/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Kuro-Token': token },
            body: JSON.stringify({ filename: bkp.filename })
          });
          if (dRes.ok) {
            showToast('Backup archive deleted 🗑️');
            fetchBackupsList();
          } else {
            showToast('Failed to delete backup');
          }
        } catch (_) {
          showToast('Network error deleting backup');
        }
      });

      DOM.backupListContainer.appendChild(card);
    });
  }

  let pendingRestoreFilename = null;

  function openRestoreModal(filename) {
    pendingRestoreFilename = filename;
    if (DOM.restoreTargetName) DOM.restoreTargetName.textContent = filename;
    if (DOM.backupRestoreModal) DOM.backupRestoreModal.classList.remove('hidden');
  }

  function closeRestoreModal() {
    pendingRestoreFilename = null;
    if (DOM.backupRestoreModal) DOM.backupRestoreModal.classList.add('hidden');
  }

  async function executeRestore() {
    if (!pendingRestoreFilename) return;
    const targetFile = pendingRestoreFilename;
    const restoreFavs = DOM.chkRestoreFavs ? DOM.chkRestoreFavs.checked : true;
    const restoreCache = DOM.chkRestoreCache ? DOM.chkRestoreCache.checked : false;

    closeRestoreModal();
    showToast('⏳ Restoring database and preferences...');

    try {
      const token = localStorage.getItem('kuro_token') || '';
      const res = await fetch(`${STATE.backendBase}/api/backups/restore`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Kuro-Token': token
        },
        body: JSON.stringify({
          filename: targetFile,
          confirm: true,
          restore_favorites: restoreFavs,
          restore_cache: restoreCache
        })
      });

      const data = await res.json();
      if (res.ok && data.success) {
        showToast('✓ Backup successfully restored! Reloading application... 🔄');
        setTimeout(() => location.reload(), 1200);
      } else {
        showToast(`Restore failed: ${data.message || data.error || 'Validation error'}`);
      }
    } catch (e) {
      showToast('Network error during restoration ⚠️');
    }
  }

  async function handleCreateBackup() {
    const incFavs = DOM.chkBackupFavorites ? DOM.chkBackupFavorites.checked : true;
    const incCache = DOM.chkBackupCache ? DOM.chkBackupCache.checked : false;
    const note = DOM.inputBackupNote ? DOM.inputBackupNote.value.trim() : '';

    if (DOM.btnCreateBackup) {
      DOM.btnCreateBackup.disabled = true;
      DOM.btnCreateBackup.textContent = '⏳ Creating Backup...';
    }

    try {
      const token = localStorage.getItem('kuro_token') || '';
      const res = await fetch(`${STATE.backendBase}/api/backups`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Kuro-Token': token
        },
        body: JSON.stringify({
          backup_type: 'manual',
          include_favorites: incFavs,
          include_cache: incCache,
          note: note
        })
      });

      const data = await res.json();
      if (res.ok && data.success) {
        showToast(`✓ Backup archive created: ${data.filename} (${data.file_size_formatted}) 📦`);
        if (DOM.inputBackupNote) DOM.inputBackupNote.value = '';
        fetchBackupsList();
      } else {
        showToast(`Backup failed: ${data.message || 'Unknown error'}`);
      }
    } catch (e) {
      showToast('Network error creating backup');
    } finally {
      if (DOM.btnCreateBackup) {
        DOM.btnCreateBackup.disabled = false;
        DOM.btnCreateBackup.textContent = '📦 Create Backup Archive';
      }
    }
  }

  function handleBackupFileUpload(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;

    showToast('⏳ Uploading and validating backup archive...');
    const reader = new FileReader();
    reader.onload = async (evt) => {
      try {
        const base64Data = evt.target.result;
        const token = localStorage.getItem('kuro_token') || '';
        const res = await fetch(`${STATE.backendBase}/api/backups/upload`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Kuro-Token': token
          },
          body: JSON.stringify({
            filename: file.name,
            data: base64Data
          })
        });

        const data = await res.json();
        if (res.ok && data.status === 'uploaded') {
          showToast(`✓ Uploaded ${file.name}. Archive is valid!`);
          fetchBackupsList();
        } else {
          showToast(`Invalid archive: ${data.message || 'Validation failed'}`);
        }
      } catch (err) {
        showToast('Failed to upload backup archive ⚠️');
      }
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  }


  // --- PREFERENCES ---
  function applyPreferences() {
    // Initialize Theme & Palette
    const savedTheme = localStorage.getItem('kuro_theme') || 'kuro-dark';
    document.documentElement.dataset.theme = savedTheme;

    const savedDynamic = localStorage.getItem('kuro_dynamic_accent') !== 'false';
    const savedAccent = localStorage.getItem('kuro_accent_color') || '#38bdf8';
    const effAccent = savedDynamic ? (STATE.extractedAccent || savedAccent) : savedAccent;
    document.documentElement.style.setProperty('--dynamic-accent', effAccent);
    document.documentElement.style.setProperty('--dynamic-accent-glow', `${effAccent}44`);

    const savedUiScale = localStorage.getItem('kuro_ui_scale') || '100%';
    if (savedUiScale && savedUiScale !== '100%') {
      document.body.style.zoom = savedUiScale;
    } else {
      document.body.style.zoom = '';
    }

    const reduced = isReducedMotionActive();
    document.body.classList.toggle('reduced-motion', reduced);
    setDisplayMode(STATE.displayMode);

    if (DOM.settingDisplayMode) DOM.settingDisplayMode.value = STATE.displayMode;
    if (DOM.settingAnime) DOM.settingAnime.value = STATE.currentAnime;
    if (DOM.settingInterval) {
      DOM.settingInterval.value = STATE.intervalSeconds;
      DOM.settingIntervalLabel.textContent = `${STATE.intervalSeconds}s`;
    }
    if (DOM.settingTransition) DOM.settingTransition.value = STATE.transitionStyle;
    if (DOM.settingTransitionDuration) DOM.settingTransitionDuration.value = String(STATE.transitionDuration);
    if (DOM.settingMotion) DOM.settingMotion.value = STATE.motionStyle;
    if (DOM.settingReducedMotion) DOM.settingReducedMotion.checked = STATE.reducedMotion;
    if (DOM.settingMonitor) DOM.settingMonitor.value = STATE.targetMonitor;
    if (DOM.settingRatio) DOM.settingRatio.value = STATE.aspectRatio;
    if (DOM.settingFocalPoint) DOM.settingFocalPoint.value = STATE.focalPointMode;
    if (DOM.settingShowSeconds) DOM.settingShowSeconds.checked = STATE.showSeconds;
    if (DOM.settingDateFormat) DOM.settingDateFormat.value = STATE.dateFormat;
    if (DOM.settingSecondTz) DOM.settingSecondTz.value = STATE.secondTimeZone;
    if (DOM.settingParticles) DOM.settingParticles.checked = STATE.particlesEnabled;
    if (DOM.settingCity) DOM.settingCity.value = STATE.customCity;

    document.documentElement.style.setProperty('--transition-duration', `${STATE.transitionDuration}s`);
    document.documentElement.style.setProperty('--motion-duration', `${Math.max(STATE.intervalSeconds * 1.5, 35)}s`);

    if (window.toggleParticleLoop) {
      window.toggleParticleLoop(STATE.particlesEnabled && !reduced);
    }

    const timeRadios = document.querySelectorAll('input[name="timeFormat"]');
    timeRadios.forEach(r => r.checked = r.value === STATE.timeFormat);

    const tempRadios = document.querySelectorAll('input[name="tempUnit"]');
    tempRadios.forEach(r => r.checked = r.value === STATE.tempUnit);

    // OLED settings sync
    if (DOM.settingOledEnabled) DOM.settingOledEnabled.checked = STATE.oledEnabled;
    if (DOM.settingOledAutoDim) DOM.settingOledAutoDim.checked = STATE.oledAutoDim;
    if (DOM.settingOledIdleOpacity) {
      DOM.settingOledIdleOpacity.value = STATE.oledIdleOpacity;
      if (DOM.settingOledIdleOpacityLabel) DOM.settingOledIdleOpacityLabel.textContent = `${STATE.oledIdleOpacity}%`;
    }
    if (DOM.settingHudBaseOpacity) {
      DOM.settingHudBaseOpacity.value = STATE.hudBaseOpacity;
      if (DOM.settingHudBaseOpacityLabel) DOM.settingHudBaseOpacityLabel.textContent = `${STATE.hudBaseOpacity}%`;
    }
    if (DOM.settingOledHudShift) DOM.settingOledHudShift.checked = STATE.oledHudShift;
    if (DOM.settingOledWpShift) DOM.settingOledWpShift.checked = STATE.oledWpShift;
    if (DOM.settingOledSoftWhite) DOM.settingOledSoftWhite.checked = STATE.oledSoftWhite;
    if (DOM.settingOledScrim) {
      DOM.settingOledScrim.value = STATE.oledScrim;
      if (DOM.settingOledScrimLabel) DOM.settingOledScrimLabel.textContent = `${STATE.oledScrim}%`;
    }
    if (DOM.settingOledNightMode) DOM.settingOledNightMode.value = STATE.oledNightMode;

    applyOledPreferences();
    applySchedulerPreferencesToUI();
    applySoundscapePreferencesToUI();
  }

  // --- EVENT LISTENERS ---
  function setupEventListeners() {
    DOM.btnPlayPause.addEventListener('click', togglePlayPause);
    DOM.btnNext.addEventListener('click', () => {
      STATE.wasExplicitlySkipped = true;
      displayNextWallpaper();
    });
    DOM.btnPrev.addEventListener('click', displayPrevWallpaper);
    DOM.btnFavorite.addEventListener('click', toggleFavorite);

    DOM.btnFullscreen.addEventListener('click', () => {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
      } else {
        document.exitFullscreen().catch(() => {});
      }
    });

    DOM.btnToggleHud.addEventListener('click', () => {
      STATE.hudVisible = !STATE.hudVisible;
      document.body.classList.toggle('hud-hidden', !STATE.hudVisible);
      showToast(STATE.hudVisible ? 'HUD Restored' : 'Zen Clean Mode (Press H to restore)');
    });

    DOM.btnToggleParticles.addEventListener('click', () => {
      STATE.particlesEnabled = !STATE.particlesEnabled;
      localStorage.setItem('kuro_particles', STATE.particlesEnabled);
      if (window.toggleParticleLoop) window.toggleParticleLoop(STATE.particlesEnabled);
      showToast(STATE.particlesEnabled ? 'Ambient Particles ON' : 'Ambient Particles OFF');
    });

    DOM.quickMoods.forEach(btn => {
      btn.addEventListener('click', () => {
        DOM.quickMoods.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        STATE.currentAnime = btn.dataset.anime;
        STATE.currentCharacter = 'all';
        localStorage.setItem('kuro_anime', STATE.currentAnime);
        localStorage.setItem('kuro_character', 'all');
        if (DOM.settingAnime) DOM.settingAnime.value = STATE.currentAnime;
        updateCharacterDropdown();
        DOM.exhaustionOverlay.classList.add('hidden');
        if (STATE.currentAnime && STATE.currentAnime !== 'all') {
          backendPost('/api/interaction/select', { franchise: STATE.currentAnime }).catch(() => {});
        }
        displayNextWallpaper();
        showToast(`Anime: ${btn.textContent.trim()}`);
      });
    });

    DOM.btnSettingsOpen.addEventListener('click', openControlCenter);
    DOM.btnSettingsClose.addEventListener('click', () => closeControlCenter(true));
    if (DOM.btnSettingsCancel) DOM.btnSettingsCancel.addEventListener('click', () => closeControlCenter(true));
    if (DOM.btnSettingsSave) DOM.btnSettingsSave.addEventListener('click', saveControlCenterChanges);
    if (DOM.btnResetSection) DOM.btnResetSection.addEventListener('click', resetActiveSection);
    if (DOM.btnExportSettings) DOM.btnExportSettings.addEventListener('click', exportSettings);
    if (DOM.btnImportSettings) DOM.btnImportSettings.addEventListener('click', () => DOM.inputImportSettings && DOM.inputImportSettings.click());
    if (DOM.inputImportSettings) DOM.inputImportSettings.addEventListener('change', handleImportSettingsFile);
    if (DOM.btnFactoryReset) DOM.btnFactoryReset.addEventListener('click', factoryResetSettings);
    if (DOM.btnPurgeCache) DOM.btnPurgeCache.addEventListener('click', purgeLocalCache);

    // Backup & Recovery & Integrity listeners
    if (DOM.btnCheckIntegrity) DOM.btnCheckIntegrity.addEventListener('click', async () => {
      showToast('🔍 Running database integrity check...');
      await fetchDatabaseIntegrity();
      showToast('✓ Database integrity verified');
    });
    if (DOM.btnCreateBackup) DOM.btnCreateBackup.addEventListener('click', handleCreateBackup);
    if (DOM.btnUploadBackup) DOM.btnUploadBackup.addEventListener('click', () => DOM.inputUploadBackupFile && DOM.inputUploadBackupFile.click());
    if (DOM.inputUploadBackupFile) DOM.inputUploadBackupFile.addEventListener('change', handleBackupFileUpload);
    if (DOM.btnRefreshBackups) DOM.btnRefreshBackups.addEventListener('click', () => {
      fetchBackupsList();
      showToast('Backups list refreshed 🔄');
    });
    if (DOM.btnRestoreCancel) DOM.btnRestoreCancel.addEventListener('click', closeRestoreModal);
    if (DOM.btnRestoreConfirm) DOM.btnRestoreConfirm.addEventListener('click', executeRestore);
    if (DOM.backupRestoreModal) {
      DOM.backupRestoreModal.addEventListener('click', (e) => {
        if (e.target === DOM.backupRestoreModal) closeRestoreModal();
      });
    }

    if (DOM.navTabs) {
      DOM.navTabs.forEach(tab => {
        tab.addEventListener('click', () => switchControlCenterTab(tab.dataset.tab));
      });
    }

    if (DOM.settingsSearchInput) {
      DOM.settingsSearchInput.addEventListener('input', (e) => filterControlCenterSearch(e.target.value));
    }
    if (DOM.btnSettingsSearchClear) {
      DOM.btnSettingsSearchClear.addEventListener('click', () => {
        DOM.settingsSearchInput.value = '';
        filterControlCenterSearch('');
        DOM.settingsSearchInput.focus();
      });
    }

    if (DOM.swatches) {
      DOM.swatches.forEach(swatch => {
        swatch.addEventListener('click', () => {
          DOM.swatches.forEach(s => s.classList.remove('active'));
          swatch.classList.add('active');
          const color = swatch.dataset.color;
          if (DOM.settingVisualAccentColor) DOM.settingVisualAccentColor.value = color;
          if (DOM.settingVisualDynamicAccent) DOM.settingVisualDynamicAccent.checked = false;
          triggerVisualPreview();
        });
      });
    }

    const visualPreviewInputs = [
      DOM.settingVisualTheme,
      DOM.settingVisualDynamicAccent,
      DOM.settingVisualAccentColor,
      DOM.settingTransition,
      DOM.settingTransitionDuration,
      DOM.settingMotion,
      DOM.settingMotionIntensity,
      DOM.settingReducedMotion,
      DOM.settingParticles,
      DOM.settingParticleDensity,
      DOM.settingParticleSpeed,
      DOM.settingHudBaseOpacity,
      DOM.settingOledIdleOpacity,
      DOM.settingOledScrim,
      DOM.settingOledNightMode,
      DOM.settingUiScale,
      DOM.settingWpFitMode,
      DOM.settingCompBlurEnabled,
      DOM.settingCompBlurIntensity
    ];
    visualPreviewInputs.forEach(input => {
      if (!input) return;
      input.addEventListener('input', triggerVisualPreview);
      input.addEventListener('change', triggerVisualPreview);
    });

    if (DOM.settingCompBlurIntensity && DOM.settingCompBlurLabel) {
      DOM.settingCompBlurIntensity.addEventListener('input', (e) => {
        DOM.settingCompBlurLabel.textContent = `${e.target.value}px`;
      });
    }

    if (DOM.settingPerfPrefetch && DOM.settingPerfPrefetchLabel) {
      DOM.settingPerfPrefetch.addEventListener('input', (e) => {
        DOM.settingPerfPrefetchLabel.textContent = `${e.target.value} slides`;
        validateControlCenter();
      });
    }

    if (DOM.settingPerfCacheLimit && DOM.settingPerfCacheLimitLabel) {
      DOM.settingPerfCacheLimit.addEventListener('input', (e) => {
        const cl = parseInt(e.target.value, 10);
        DOM.settingPerfCacheLimitLabel.textContent = `${cl} MB (${(cl/1024).toFixed(1)} GB)`;
        validateControlCenter();
      });
    }

    DOM.settingsModal.addEventListener('click', (e) => {
      if (e.target === DOM.settingsModal) closeControlCenter(true);
    });

    // Exhaustion overlay actions
    DOM.btnExhaustionSwitch.addEventListener('click', () => {
      DOM.exhaustionOverlay.classList.add('hidden');
      STATE.currentAnime = 'all';
      localStorage.setItem('kuro_anime', 'all');
      DOM.quickMoods.forEach(b => b.classList.toggle('active', b.dataset.anime === 'all'));
      if (DOM.settingAnime) DOM.settingAnime.value = 'all';
      displayNextWallpaper();
    });

    DOM.btnExhaustionSettings.addEventListener('click', () => {
      DOM.exhaustionOverlay.classList.add('hidden');
      DOM.settingsModal.classList.remove('hidden');
    });

    if (DOM.settingAnime) {
      DOM.settingAnime.addEventListener('change', (e) => {
        STATE.currentAnime = e.target.value;
        STATE.currentCharacter = 'all';
        localStorage.setItem('kuro_anime', STATE.currentAnime);
        localStorage.setItem('kuro_character', 'all');
        DOM.quickMoods.forEach(b => {
          b.classList.toggle('active', b.dataset.anime === STATE.currentAnime);
        });
        updateCharacterDropdown();
        DOM.exhaustionOverlay.classList.add('hidden');
        if (STATE.currentAnime && STATE.currentAnime !== 'all') {
          backendPost('/api/interaction/select', { franchise: STATE.currentAnime }).catch(() => {});
        }
        displayNextWallpaper();
        showToast(`Anime Filter: ${STATE.currentAnime === 'all' ? 'Random Anime' : STATE.currentAnime}`);
      });
    }

    if (DOM.settingCharacter) {
      DOM.settingCharacter.addEventListener('change', (e) => {
        STATE.currentCharacter = e.target.value;
        localStorage.setItem('kuro_character', STATE.currentCharacter);
        DOM.exhaustionOverlay.classList.add('hidden');
        displayNextWallpaper();
        showToast(`Character Filter: ${STATE.currentCharacter === 'all' ? 'All Characters' : STATE.currentCharacter}`);
      });
    }

    // Intelligent Scheduling event listeners
    if (DOM.settingScheduleStrategy) {
      DOM.settingScheduleStrategy.addEventListener('change', (e) => {
        STATE.schedulerStrategy = e.target.value;
        updateSchedulerSubpanels(STATE.schedulerStrategy);
        updateSchedulerSettingsFromUI();
        showToast(`Scheduling Strategy: ${DOM.settingScheduleStrategy.options[DOM.settingScheduleStrategy.selectedIndex].text}`);
      });
    }

    if (DOM.settingInterval) {
      DOM.settingInterval.addEventListener('input', (e) => {
        STATE.schedulerFixedSec = parseInt(e.target.value, 10);
        STATE.intervalSeconds = STATE.schedulerFixedSec;
        if (DOM.settingIntervalLabel) DOM.settingIntervalLabel.textContent = `${STATE.schedulerFixedSec}s`;
        updateSchedulerSettingsFromUI();
      });
    }

    if (DOM.settingRandomMin) {
      DOM.settingRandomMin.addEventListener('input', (e) => {
        STATE.schedulerRandMin = parseInt(e.target.value, 10);
        if (DOM.settingRandomMinLabel) DOM.settingRandomMinLabel.textContent = `${STATE.schedulerRandMin}s`;
        if (STATE.schedulerRandMax < STATE.schedulerRandMin) {
          STATE.schedulerRandMax = STATE.schedulerRandMin;
          if (DOM.settingRandomMax) DOM.settingRandomMax.value = STATE.schedulerRandMax;
          if (DOM.settingRandomMaxLabel) DOM.settingRandomMaxLabel.textContent = `${STATE.schedulerRandMax}s`;
        }
        updateSchedulerSettingsFromUI();
      });
    }

    if (DOM.settingRandomMax) {
      DOM.settingRandomMax.addEventListener('input', (e) => {
        STATE.schedulerRandMax = parseInt(e.target.value, 10);
        if (DOM.settingRandomMaxLabel) DOM.settingRandomMaxLabel.textContent = `${STATE.schedulerRandMax}s`;
        if (STATE.schedulerRandMin > STATE.schedulerRandMax) {
          STATE.schedulerRandMin = STATE.schedulerRandMax;
          if (DOM.settingRandomMin) DOM.settingRandomMin.value = STATE.schedulerRandMin;
          if (DOM.settingRandomMinLabel) DOM.settingRandomMinLabel.textContent = `${STATE.schedulerRandMin}s`;
        }
        updateSchedulerSettingsFromUI();
      });
    }

    if (DOM.settingDaySec) {
      DOM.settingDaySec.addEventListener('change', (e) => {
        STATE.schedulerDaySec = Math.max(5, Math.min(300, parseInt(e.target.value, 10) || 25));
        e.target.value = STATE.schedulerDaySec;
        updateSchedulerSettingsFromUI();
      });
    }

    if (DOM.settingEveSec) {
      DOM.settingEveSec.addEventListener('change', (e) => {
        STATE.schedulerEveSec = Math.max(5, Math.min(300, parseInt(e.target.value, 10) || 35));
        e.target.value = STATE.schedulerEveSec;
        updateSchedulerSettingsFromUI();
      });
    }

    if (DOM.settingNightSec) {
      DOM.settingNightSec.addEventListener('change', (e) => {
        STATE.schedulerNightSec = Math.max(5, Math.min(300, parseInt(e.target.value, 10) || 60));
        e.target.value = STATE.schedulerNightSec;
        updateSchedulerSettingsFromUI();
      });
    }

    if (DOM.settingCinematicSec) {
      DOM.settingCinematicSec.addEventListener('input', (e) => {
        STATE.schedulerCinematicSec = parseInt(e.target.value, 10);
        if (DOM.settingCinematicSecLabel) DOM.settingCinematicSecLabel.textContent = `${STATE.schedulerCinematicSec}s`;
        updateSchedulerSettingsFromUI();
      });
    }

    if (DOM.settingDashboardSec) {
      DOM.settingDashboardSec.addEventListener('input', (e) => {
        STATE.schedulerDashboardSec = parseInt(e.target.value, 10);
        if (DOM.settingDashboardSecLabel) DOM.settingDashboardSecLabel.textContent = `${STATE.schedulerDashboardSec}s`;
        updateSchedulerSettingsFromUI();
      });
    }

    if (DOM.settingFranchiseRotInterval) {
      DOM.settingFranchiseRotInterval.addEventListener('input', (e) => {
        STATE.franchiseRotationInterval = parseInt(e.target.value, 10);
        if (DOM.settingFranchiseRotLabel) DOM.settingFranchiseRotLabel.textContent = `${STATE.franchiseRotationInterval} slides`;
        updateSchedulerSettingsFromUI();
      });
    }

    if (DOM.settingScheduleQualityBonus) {
      DOM.settingScheduleQualityBonus.addEventListener('change', (e) => {
        STATE.schedulerQualityBonus = e.target.checked;
        updateSchedulerSettingsFromUI();
        showToast(STATE.schedulerQualityBonus ? 'Quality viewing bonus: ENABLED' : 'Quality viewing bonus: DISABLED');
      });
    }

    if (DOM.settingSchedulePauseHidden) {
      DOM.settingSchedulePauseHidden.addEventListener('change', (e) => {
        STATE.pauseOnHidden = e.target.checked;
        updateSchedulerSettingsFromUI();
        showToast(STATE.pauseOnHidden ? 'Pause on hidden: ENABLED' : 'Pause on hidden: DISABLED');
      });
    }

    // Tab visibility change listener: pause timer when app is minimized or tab is hidden
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        stopFpsMeter();
        if (STATE.diagnosticsPollTimer) {
          clearInterval(STATE.diagnosticsPollTimer);
          STATE.diagnosticsPollTimer = null;
        }

        if (STATE.pauseOnHidden && !STATE.isPaused && STATE.schedulerStrategy !== 'manual') {
          STATE.savedElapsed = performance.now() - (STATE.slideStartTime || performance.now());
          STATE.isPausedForHidden = true;
          cancelAnimationFrame(STATE.progressRaf);
          clearTimeout(STATE.timer);
          if (DOM.progressTimerText) {
            const rem = Math.max(0, Math.ceil((STATE.currentSlideDuration - STATE.savedElapsed) / 1000));
            DOM.progressTimerText.textContent = `Hidden (Paused · ${rem}s left)`;
          }
        }
      } else {
        startFpsMeter();
        if (STATE.diagnosticsOpen && !STATE.diagnosticsPollTimer) {
          updateDiagnosticsMetrics();
          STATE.diagnosticsPollTimer = setInterval(() => {
            if (!document.hidden && STATE.diagnosticsOpen) {
              updateDiagnosticsMetrics();
            }
          }, 2500);
        }

        if (STATE.pauseOnHidden && STATE.isPausedForHidden) {
          resumeSlideTimerFromVisibility();
        }
      }
    });

    DOM.settingTransition.addEventListener('change', (e) => {
      STATE.transitionStyle = e.target.value;
      localStorage.setItem('kuro_transition', STATE.transitionStyle);
      applyPreferences();
      showToast(`Transition Effect: ${DOM.settingTransition.options[DOM.settingTransition.selectedIndex].text}`);
    });

    if (DOM.settingTransitionDuration) {
      DOM.settingTransitionDuration.addEventListener('change', (e) => {
        STATE.transitionDuration = parseFloat(e.target.value);
        localStorage.setItem('kuro_transition_duration', STATE.transitionDuration);
        document.documentElement.style.setProperty('--transition-duration', `${STATE.transitionDuration}s`);
        showToast(`Transition Speed: ${DOM.settingTransitionDuration.options[DOM.settingTransitionDuration.selectedIndex].text}`);
      });
    }

    if (DOM.settingMotion) {
      DOM.settingMotion.addEventListener('change', (e) => {
        STATE.motionStyle = e.target.value;
        localStorage.setItem('kuro_motion', STATE.motionStyle);
        showToast(`Ambient Motion: ${DOM.settingMotion.options[DOM.settingMotion.selectedIndex].text}`);
      });
    }

    if (DOM.settingReducedMotion) {
      DOM.settingReducedMotion.addEventListener('change', (e) => {
        STATE.reducedMotion = e.target.checked;
        localStorage.setItem('kuro_reduced_motion', STATE.reducedMotion);
        applyPreferences();
        showToast(STATE.reducedMotion ? 'Reduced Motion: Forced ON' : 'Reduced Motion: Standard Mode');
      });
    }

    // System OS prefers-reduced-motion listener
    try {
      const motionMedia = window.matchMedia('(prefers-reduced-motion: reduce)');
      if (motionMedia && motionMedia.addEventListener) {
        motionMedia.addEventListener('change', () => applyPreferences());
      }
    } catch (_) {}

    if (DOM.settingMonitor) {
      DOM.settingMonitor.addEventListener('change', (e) => {
        STATE.targetMonitor = e.target.value;
        localStorage.setItem('kuro_target_monitor', STATE.targetMonitor);
        if (STATE.targetMonitor === 'auto') {
          showToast('Target Monitor: Auto (Viewport Match)');
          if (DOM.statActiveMonitor) {
            const count = STATE.connectedMonitors.length;
            DOM.statActiveMonitor.textContent = `Auto (${count} display${count === 1 ? '' : 's'})`;
          }
        } else {
          const mon = STATE.connectedMonitors.find(m => m.name === STATE.targetMonitor);
          showToast(`Target Monitor: ${STATE.targetMonitor} (${mon ? mon.profile : ''})`);
          if (DOM.statActiveMonitor && mon) {
            DOM.statActiveMonitor.textContent = `${mon.name} (${mon.profile || `${mon.width}×${mon.height}`})`;
          }
        }
        displayNextWallpaper();
      });
    }

    if (DOM.settingRatio) {
      DOM.settingRatio.addEventListener('change', (e) => {
        STATE.aspectRatio = e.target.value;
        localStorage.setItem('kuro_ratio', STATE.aspectRatio);
        displayNextWallpaper();
      });
    }

    if (DOM.settingFocalPoint) {
      DOM.settingFocalPoint.addEventListener('change', (e) => {
        STATE.focalPointMode = e.target.value;
        localStorage.setItem('kuro_focal_point', STATE.focalPointMode);
        showToast(`Focal Point: ${DOM.settingFocalPoint.options[DOM.settingFocalPoint.selectedIndex].text}`);
        if (STATE.currentWallpaper && STATE.currentWallpaper._preloadedImg) {
          const focal = calculateFocalPoint(STATE.currentWallpaper._preloadedImg);
          const currentLayer = STATE.activeLayer === 'a' ? DOM.layerA : DOM.layerB;
          currentLayer.style.setProperty('--focal-x', `${focal.x}%`);
          currentLayer.style.setProperty('--focal-y', `${focal.y}%`);
        }
      });
    }

    DOM.settingParticles.addEventListener('change', (e) => {
      STATE.particlesEnabled = e.target.checked;
      localStorage.setItem('kuro_particles', STATE.particlesEnabled);
      if (window.toggleParticleLoop) window.toggleParticleLoop(STATE.particlesEnabled);
    });

    if (DOM.settingShowSeconds) {
      DOM.settingShowSeconds.addEventListener('change', (e) => {
        STATE.showSeconds = e.target.checked;
        localStorage.setItem('kuro_show_seconds', STATE.showSeconds);
        showToast(STATE.showSeconds ? 'Clock Seconds: Visible' : 'Clock Seconds: Hidden in Ambient');
      });
    }

    if (DOM.settingDateFormat) {
      DOM.settingDateFormat.addEventListener('change', (e) => {
        STATE.dateFormat = e.target.value;
        localStorage.setItem('kuro_date_format', STATE.dateFormat);
        showToast(`Date Format: ${DOM.settingDateFormat.options[DOM.settingDateFormat.selectedIndex].text}`);
      });
    }

    if (DOM.settingSecondTz) {
      DOM.settingSecondTz.addEventListener('change', (e) => {
        STATE.secondTimeZone = e.target.value;
        localStorage.setItem('kuro_second_tz', STATE.secondTimeZone);
        showToast(`Dual Clock: ${DOM.settingSecondTz.options[DOM.settingSecondTz.selectedIndex].text}`);
      });
    }

    document.querySelectorAll('input[name="tempUnit"]').forEach(r => {
      r.addEventListener('change', (e) => {
        STATE.tempUnit = e.target.value;
        localStorage.setItem('kuro_temp_unit', STATE.tempUnit);
        showToast(`Temperature Unit: °${STATE.tempUnit}`);
        setupWeather();
      });
    });

    document.querySelectorAll('input[name="timeFormat"]').forEach(r => {
      r.addEventListener('change', (e) => {
        STATE.timeFormat = e.target.value;
        localStorage.setItem('kuro_timeformat', STATE.timeFormat);
        setupWeather();
      });
    });

    DOM.btnSaveCity.addEventListener('click', () => {
      STATE.customCity = DOM.settingCity.value.trim();
      localStorage.setItem('kuro_city', STATE.customCity);
      setupWeather();
      showToast(STATE.customCity ? `Weather Location: ${STATE.customCity}` : 'Weather: Auto IP Location');
    });

    if (DOM.btnAutoCity) {
      DOM.btnAutoCity.addEventListener('click', () => {
        STATE.customCity = '';
        localStorage.removeItem('kuro_city');
        if (DOM.settingCity) DOM.settingCity.value = '';
        setupWeather();
        showToast('Weather: Reset to Auto IP detection');
      });
    }

    // OLED Care & Burn-in Prevention Event Listeners
    if (DOM.settingOledEnabled) {
      DOM.settingOledEnabled.addEventListener('change', (e) => {
        STATE.oledEnabled = e.target.checked;
        localStorage.setItem('kuro_oled_enabled', STATE.oledEnabled);
        applyOledPreferences();
        showToast(STATE.oledEnabled ? 'OLED Care Mode: Active 🛡️' : 'OLED Care Mode: Disabled');
      });
    }

    if (DOM.settingOledAutoDim) {
      DOM.settingOledAutoDim.addEventListener('change', (e) => {
        STATE.oledAutoDim = e.target.checked;
        localStorage.setItem('kuro_oled_auto_dim', STATE.oledAutoDim);
        applyOledPreferences();
        showToast(STATE.oledAutoDim ? 'Inactivity Auto-Dim: Enabled' : 'Inactivity Auto-Dim: Disabled');
      });
    }

    if (DOM.settingOledIdleOpacity) {
      DOM.settingOledIdleOpacity.addEventListener('input', (e) => {
        STATE.oledIdleOpacity = parseInt(e.target.value, 10);
        localStorage.setItem('kuro_oled_idle_opacity', STATE.oledIdleOpacity);
        if (DOM.settingOledIdleOpacityLabel) DOM.settingOledIdleOpacityLabel.textContent = `${STATE.oledIdleOpacity}%`;
        applyOledPreferences();
      });
    }

    if (DOM.settingHudBaseOpacity) {
      DOM.settingHudBaseOpacity.addEventListener('input', (e) => {
        STATE.hudBaseOpacity = parseInt(e.target.value, 10);
        localStorage.setItem('kuro_hud_base_opacity', STATE.hudBaseOpacity);
        if (DOM.settingHudBaseOpacityLabel) DOM.settingHudBaseOpacityLabel.textContent = `${STATE.hudBaseOpacity}%`;
        applyOledPreferences();
      });
    }

    if (DOM.settingOledHudShift) {
      DOM.settingOledHudShift.addEventListener('change', (e) => {
        STATE.oledHudShift = e.target.checked;
        localStorage.setItem('kuro_oled_hud_shift', STATE.oledHudShift);
        applyOledPreferences();
        showToast(STATE.oledHudShift ? 'HUD Pixel-Shift: Enabled (10-15m)' : 'HUD Pixel-Shift: Disabled');
      });
    }

    if (DOM.settingOledWpShift) {
      DOM.settingOledWpShift.addEventListener('change', (e) => {
        STATE.oledWpShift = e.target.checked;
        localStorage.setItem('kuro_oled_wp_shift', STATE.oledWpShift);
        applyOledPreferences();
        showToast(STATE.oledWpShift ? 'Wallpaper Drift: Enabled' : 'Wallpaper Drift: Disabled');
      });
    }

    if (DOM.settingOledSoftWhite) {
      DOM.settingOledSoftWhite.addEventListener('change', (e) => {
        STATE.oledSoftWhite = e.target.checked;
        localStorage.setItem('kuro_oled_soft_white', STATE.oledSoftWhite);
        applyOledPreferences();
        showToast(STATE.oledSoftWhite ? 'Soft Luminance: Active (Anti-Burn-In)' : 'Standard Peak Luminance');
      });
    }

    if (DOM.settingOledScrim) {
      DOM.settingOledScrim.addEventListener('input', (e) => {
        STATE.oledScrim = parseInt(e.target.value, 10);
        localStorage.setItem('kuro_oled_scrim', STATE.oledScrim);
        if (DOM.settingOledScrimLabel) DOM.settingOledScrimLabel.textContent = `${STATE.oledScrim}%`;
        applyOledPreferences();
      });
    }

    if (DOM.settingOledNightMode) {
      DOM.settingOledNightMode.addEventListener('change', (e) => {
        STATE.oledNightMode = e.target.value;
        localStorage.setItem('kuro_oled_night_mode', STATE.oledNightMode);
        applyOledPreferences();
        showToast(`Night Mode: ${DOM.settingOledNightMode.options[DOM.settingOledNightMode.selectedIndex].text}`);
      });
    }

    // Intelligent Personalization & Recommendations Listeners
    if (DOM.settingRecEnabled) {
      DOM.settingRecEnabled.addEventListener('change', async (e) => {
        const enabled = e.target.checked;
        if (DOM.recSubcontrols) {
          DOM.recSubcontrols.style.opacity = enabled ? '1' : '0.4';
          DOM.recSubcontrols.style.pointerEvents = enabled ? 'auto' : 'none';
        }
        try {
          await backendPost('/api/recommendations/toggle', { enabled });
          showToast(enabled ? 'Personalization enabled' : 'Personalization disabled (uniform discovery)');
        } catch (err) {
          console.warn('[Kuro] Error toggling personalization:', err);
        }
      });
    }

    if (DOM.settingRecDiversity) {
      DOM.settingRecDiversity.addEventListener('change', async (e) => {
        const diversity_penalty = e.target.checked;
        try {
          await backendPost('/api/recommendations/toggle', { diversity_penalty });
          showToast(diversity_penalty ? 'Diversity Guard enabled' : 'Diversity Guard disabled');
        } catch (err) {
          console.warn('[Kuro] Error toggling diversity guard:', err);
        }
      });
    }

    if (DOM.btnRecApplyBias) {
      DOM.btnRecApplyBias.addEventListener('click', async () => {
        const franchise = DOM.recManualFranchiseSelect ? DOM.recManualFranchiseSelect.value.trim() : '';
        const score = DOM.recManualScoreInput ? parseFloat(DOM.recManualScoreInput.value) : 0;
        if (!franchise) {
          showToast('Please select a franchise first.');
          return;
        }
        if (isNaN(score)) {
          showToast('Invalid bias score.');
          return;
        }
        try {
          await backendPost('/api/recommendations/adjust', {
            entity_type: 'franchise',
            entity_name: franchise,
            manual_score: score
          });
          showToast(`Applied ${score >= 0 ? '+' : ''}${score} bias to ${franchise}`);
          await loadPersonalizationProfile();
        } catch (err) {
          showToast('Failed to apply preference adjustment');
        }
      });
    }

    if (DOM.btnRecReset) {
      DOM.btnRecReset.addEventListener('click', async () => {
        if (confirm('Reset recommendation learning history? This clears learned scores and interaction events, returning recommendations to neutral.')) {
          try {
            await backendPost('/api/recommendations/reset', {});
            showToast('Learning history reset to neutral.');
            await loadPersonalizationProfile();
          } catch (err) {
            showToast('Failed to reset recommendations');
          }
        }
      });
    }

    // Quality Scoring Event Listeners
    if (DOM.settingQualityThreshold) {
      DOM.settingQualityThreshold.addEventListener('input', (e) => {
        if (DOM.settingQualityThresholdLabel) {
          DOM.settingQualityThresholdLabel.textContent = `${e.target.value} / 100`;
        }
      });
      DOM.settingQualityThreshold.addEventListener('change', updateQualitySettingsFromUI);
    }

    if (DOM.settingQualityNativeRes) {
      DOM.settingQualityNativeRes.addEventListener('change', updateQualitySettingsFromUI);
    }
    if (DOM.settingQualityAspectRatio) {
      DOM.settingQualityAspectRatio.addEventListener('change', updateQualitySettingsFromUI);
    }
    if (DOM.settingQualityAvoidBright) {
      DOM.settingQualityAvoidBright.addEventListener('change', updateQualitySettingsFromUI);
    }
    if (DOM.settingQualityAvoidDark) {
      DOM.settingQualityAvoidDark.addEventListener('change', updateQualitySettingsFromUI);
    }
    if (DOM.settingQualityPopWeight) {
      DOM.settingQualityPopWeight.addEventListener('change', updateQualitySettingsFromUI);
    }
    if (DOM.btnQualityRescore) {
      DOM.btnQualityRescore.addEventListener('click', rescoreQualityCatalog);
    }

    // Synchronized Reset: clears SQLite backend + client session
    DOM.btnClearHistory.addEventListener('click', async () => {
      if (confirm('Reset wallpaper history? This will allow previously viewed wallpapers to be discovered again.')) {
        try {
          await backendPost('/api/reset-history', {});
        } catch (_) {}
        STATE.sessionHistory = [];
        STATE.sessionHistoryIndex = -1;
        DOM.exhaustionOverlay.classList.add('hidden');
        DOM.statTotalSeen.textContent = 0;
        showToast('Wallpaper history reset successfully.');
        displayNextWallpaper();
      }
    });

    // Display Mode Switcher event listeners
    if (DOM.modePills && DOM.modePills.length > 0) {
      DOM.modePills.forEach(pill => {
        pill.addEventListener('click', () => setDisplayMode(pill.dataset.mode));
      });
    }

    if (DOM.settingDisplayMode) {
      DOM.settingDisplayMode.addEventListener('change', (e) => setDisplayMode(e.target.value));
    }

    // Keyboard Shortcuts (Safe against typing in input/select/textarea)
    window.addEventListener('keydown', (e) => {
      if (e.target.matches && e.target.matches('input, select, textarea, [contenteditable="true"]')) return;

      if ((e.ctrlKey || e.metaKey) && (e.key === 'q' || e.key === 'Q')) {
        e.preventDefault();
        exitScreensaverCleanly();
        return;
      }

      // Sub-modal shortcuts when Artwork Information Panel is active
      if (STATE.artworkInfoModalOpen) {
        if (e.key === 'c' || e.key === 'C') {
          e.preventDefault();
          if (DOM.btnArtinfoCopyUrl) DOM.btnArtinfoCopyUrl.click();
          return;
        }
        if (e.key === 'v' || e.key === 'V') {
          e.preventDefault();
          if (DOM.btnArtinfoViewOrig) DOM.btnArtinfoViewOrig.click();
          return;
        }
        if (e.key === 'h' || e.key === 'H') {
          e.preventDefault();
          if (DOM.btnArtinfoHide) DOM.btnArtinfoHide.click();
          return;
        }
        if (e.key === 'r' || e.key === 'R') {
          e.preventDefault();
          if (DOM.btnArtinfoReport) DOM.btnArtinfoReport.click();
          return;
        }
      }

      switch (e.key) {
        case ' ':
          e.preventDefault();
          togglePlayPause();
          break;
        case 'ArrowRight':
          e.preventDefault();
          STATE.wasExplicitlySkipped = true;
          displayNextWallpaper();
          break;
        case 'ArrowLeft':
          e.preventDefault();
          displayPrevWallpaper();
          break;
        case 'i':
        case 'I':
          toggleArtworkInfoModal();
          break;
        case 'o':
        case 'O':
          if (STATE.artworkInfoModalOpen) {
            if (DOM.btnArtinfoOpenSource) DOM.btnArtinfoOpenSource.click();
          } else {
            toggleCompositionModal();
          }
          break;
        case 'm':
        case 'M':
          cycleDisplayMode();
          break;
        case 'f':
        case 'F':
          DOM.btnFullscreen.click();
          break;
        case 'h':
        case 'H':
          DOM.btnToggleHud.click();
          break;
        case 'l':
        case 'L':
          toggleFavorite();
          break;
        case 'b':
        case 'B':
          if (STATE.artworkInfoModalOpen) {
            if (DOM.btnArtinfoBlacklist) DOM.btnArtinfoBlacklist.click();
          } else {
            openLibraryModal();
          }
          break;
        case 'x':
        case 'X':
          blacklistCurrentWallpaper();
          break;
        case 'c':
        case 'C':
          DOM.btnToggleParticles.click();
          break;
        case 's':
        case 'S':
          if (DOM.settingsModal.classList.contains('hidden')) {
            openControlCenter();
          } else {
            closeControlCenter(true);
          }
          break;
        case 'd':
        case 'D':
          toggleDiagnosticsOverlay();
          break;
        case 'a':
        case 'A':
          toggleSoundscapeMute();
          break;
        case '[':
          setSoundscapeVolume(Math.max(0, STATE.soundscapeVolume - 5));
          showToast(`Soundscape Volume: ${STATE.soundscapeVolume}% 🔉`);
          break;
        case ']':
          setSoundscapeVolume(Math.min(100, STATE.soundscapeVolume + 5));
          showToast(`Soundscape Volume: ${STATE.soundscapeVolume}% 🔊`);
          break;
        case 'n':
        case 'N':
          cycleSoundscapeTrack(true);
          break;
        case 'p':
        case 'P':
          cycleSoundscapeTrack(false);
          break;
        case 'y':
        case 'Y':
          toggleHistoryExplorer();
          break;
        case 'Escape':
          if (STATE.diagnosticsOpen) {
            toggleDiagnosticsOverlay(false);
            break;
          }
          closeArtworkInfoModal();
          closeCompositionModal();
          closeLibraryModal();
          closeHistoryExplorer();
          if (DOM.collectionPromptModal) DOM.collectionPromptModal.classList.add('hidden');
          if (DOM.addToCollectionModal) DOM.addToCollectionModal.classList.add('hidden');
          closeControlCenter(true);
          DOM.exhaustionOverlay.classList.add('hidden');
          break;
      }
    });

    // Library Modal & Collection Management Listeners
    if (DOM.btnLibraryOpen) DOM.btnLibraryOpen.addEventListener('click', () => openLibraryModal());
    if (DOM.btnLibraryClose) DOM.btnLibraryClose.addEventListener('click', closeLibraryModal);
    if (DOM.btnBlacklistCurrent) DOM.btnBlacklistCurrent.addEventListener('click', blacklistCurrentWallpaper);

    if (DOM.libTabBtns) {
      DOM.libTabBtns.forEach(btn => {
        btn.addEventListener('click', () => switchLibraryTab(btn.dataset.tab));
      });
    }

    if (DOM.favSearchInput) {
      DOM.favSearchInput.addEventListener('input', (e) => {
        if (DOM.favSearchClear) DOM.favSearchClear.classList.toggle('hidden', !e.target.value);
        debounce(loadFavoritesTab, 250)();
      });
    }
    if (DOM.favSearchClear) {
      DOM.favSearchClear.addEventListener('click', () => {
        DOM.favSearchInput.value = '';
        DOM.favSearchClear.classList.add('hidden');
        loadFavoritesTab();
      });
    }
    if (DOM.favFilterFranchise) DOM.favFilterFranchise.addEventListener('change', loadFavoritesTab);
    if (DOM.favFilterRes) DOM.favFilterRes.addEventListener('change', loadFavoritesTab);
    if (DOM.btnRefreshFavorites) DOM.btnRefreshFavorites.addEventListener('click', loadFavoritesTab);

    if (DOM.btnNewCollection) DOM.btnNewCollection.addEventListener('click', () => openPromptModal('create'));
    if (DOM.btnRenameCol) DOM.btnRenameCol.addEventListener('click', () => openPromptModal('rename'));
    if (DOM.btnDeleteCol) DOM.btnDeleteCol.addEventListener('click', deleteActiveCollection);
    if (DOM.colSearchInput) DOM.colSearchInput.addEventListener('input', debounce(loadActiveCollectionItems, 250));
    if (DOM.colFilterFranchise) DOM.colFilterFranchise.addEventListener('change', loadActiveCollectionItems);
    if (DOM.colFilterRes) DOM.colFilterRes.addEventListener('change', loadActiveCollectionItems);

    if (DOM.btnPurgeCache) DOM.btnPurgeCache.addEventListener('click', purgePrefetchCache);
    if (DOM.btnRefreshStorage) DOM.btnRefreshStorage.addEventListener('click', loadStatsTab);

    if (DOM.btnPromptClose) DOM.btnPromptClose.addEventListener('click', () => DOM.collectionPromptModal.classList.add('hidden'));
    if (DOM.btnPromptCancel) DOM.btnPromptCancel.addEventListener('click', () => DOM.collectionPromptModal.classList.add('hidden'));
    if (DOM.btnPromptConfirm) DOM.btnPromptConfirm.addEventListener('click', submitPromptModal);
    if (DOM.btnAddColClose) DOM.btnAddColClose.addEventListener('click', () => DOM.addToCollectionModal.classList.add('hidden'));

    // Exit & Windows System Integration Listeners
    if (DOM.btnExitScreensaver) DOM.btnExitScreensaver.addEventListener('click', exitScreensaverCleanly);
    if (DOM.btnSettingsExit) DOM.btnSettingsExit.addEventListener('click', exitScreensaverCleanly);

    if (DOM.settingWinStartup) {
      DOM.settingWinStartup.addEventListener('change', async (e) => {
        const enable = e.target.checked;
        try {
          await backendPost('/api/launcher/config', { autostart_on_boot: enable });
          showToast(enable ? 'Startup enabled: screensaver launches on Windows boot' : 'Startup disabled');
        } catch (_) {}
      });
    }

    if (DOM.settingLaunchMode) {
      DOM.settingLaunchMode.addEventListener('change', async (e) => {
        const mode = e.target.value;
        try {
          await backendPost('/api/launcher/config', { mode });
          showToast(`Default mode saved: ${mode.toUpperCase()}`);
        } catch (_) {}
      });
    }

    // Ambient Soundscape UI Event Listeners
    if (DOM.btnSoundscapeToggle) DOM.btnSoundscapeToggle.addEventListener('click', toggleSoundscapeMute);
    if (DOM.btnSoundscapeMute) DOM.btnSoundscapeMute.addEventListener('click', toggleSoundscapeMute);
    if (DOM.settingSoundscapeEnabled) DOM.settingSoundscapeEnabled.addEventListener('change', updateSoundscapeSettingsFromUI);
    if (DOM.settingSoundscapeTrack) DOM.settingSoundscapeTrack.addEventListener('change', updateSoundscapeSettingsFromUI);
    if (DOM.settingSoundscapeVolume) DOM.settingSoundscapeVolume.addEventListener('input', updateSoundscapeSettingsFromUI);
    if (DOM.settingSoundscapeCrossfade) DOM.settingSoundscapeCrossfade.addEventListener('input', updateSoundscapeSettingsFromUI);

    // Stop soundscape playback when window unloads
    window.addEventListener('beforeunload', stopSoundscapeAudio);
  }

  // --- PERSONAL LIBRARY & COLLECTION CONTROLLER ---
  let currentLibraryTab = 'favorites';
  let allCollections = [];
  let activeCollectionId = null;
  let targetWallpaperForCollection = null;
  let promptAction = 'create'; // 'create' | 'rename'

  function openLibraryModal(tab = 'favorites') {
    if (!DOM.libraryModal) return;
    DOM.libraryModal.classList.remove('hidden');
    populateFranchiseFilterDropdowns();
    switchLibraryTab(tab);
  }

  function closeLibraryModal() {
    if (!DOM.libraryModal) return;
    DOM.libraryModal.classList.add('hidden');
  }

  function switchLibraryTab(tabName) {
    if (tabName === 'history') {
      closeLibraryModal();
      openHistoryExplorer();
      return;
    }
    currentLibraryTab = tabName;
    if (DOM.libTabBtns) {
      DOM.libTabBtns.forEach(btn => btn.classList.toggle('active', btn.dataset.tab === tabName));
    }
    if (DOM.libTabPanels) {
      DOM.libTabPanels.forEach(panel => {
        const isMatch = panel.id === `tab-content-${tabName}`;
        panel.classList.toggle('active', isMatch);
      });
    }

    if (tabName === 'favorites') loadFavoritesTab();
    else if (tabName === 'collections') loadCollectionsTab();
    else if (tabName === 'blacklist') loadBlacklistTab();
    else if (tabName === 'stats') loadStatsTab();
  }

  function populateFranchiseFilterDropdowns() {
    const list = STATE.franchisesList || [];
    const makeOptions = (selectEl) => {
      if (!selectEl) return;
      const currentVal = selectEl.value;
      let html = '<option value="all">All Franchises</option>';
      list.forEach(f => {
        html += `<option value="${escapeHtml(f.name)}">${escapeHtml(f.name)}</option>`;
      });
      selectEl.innerHTML = html;
      selectEl.value = currentVal || 'all';
    };
    makeOptions(DOM.favFilterFranchise);
    makeOptions(DOM.colFilterFranchise);
  }

  // --- TAB 1: FAVORITES ---
  async function loadFavoritesTab() {
    if (!DOM.favoritesGrid) return;
    DOM.favoritesGrid.innerHTML = '<div style="color: #94A3B8; padding: 2rem;">Loading favorites...</div>';

    const franchise = DOM.favFilterFranchise ? DOM.favFilterFranchise.value : 'all';
    const resolution = DOM.favFilterRes ? DOM.favFilterRes.value : 'all';
    const search = DOM.favSearchInput ? DOM.favSearchInput.value.trim() : '';

    const params = new URLSearchParams();
    if (franchise && franchise !== 'all') params.append('franchise', franchise);
    if (resolution && resolution !== 'all') params.append('resolution', resolution);
    if (search) params.append('search', search);

    try {
      const res = await fetch(`${STATE.backendBase}/api/favorites?${params.toString()}`);
      if (!res.ok) throw new Error('Failed to load favorites');
      const items = await res.json();

      if (DOM.libTabFavCount) DOM.libTabFavCount.textContent = items.length;
      if (DOM.statFavoritesCount) DOM.statFavoritesCount.textContent = items.length;

      if (!items || items.length === 0) {
        DOM.favoritesGrid.innerHTML = '';
        if (DOM.favoritesEmpty) DOM.favoritesEmpty.classList.remove('hidden');
        return;
      }

      if (DOM.favoritesEmpty) DOM.favoritesEmpty.classList.add('hidden');
      DOM.favoritesGrid.innerHTML = items.map(item => renderWallpaperCard(item, 'favorite')).join('');
      attachWallpaperCardListeners(DOM.favoritesGrid, 'favorite');
    } catch (err) {
      DOM.favoritesGrid.innerHTML = `<div style="color: #F87171; padding: 2rem;">Error: ${err.message}</div>`;
    }
  }

  // --- TAB 2: COLLECTIONS ---
  async function loadCollectionsTab() {
    if (!DOM.collectionsList) return;
    try {
      const res = await fetch(`${STATE.backendBase}/api/collections`);
      if (!res.ok) throw new Error('Failed to load collections');
      allCollections = await res.json();

      if (DOM.libTabColCount) DOM.libTabColCount.textContent = allCollections.length;

      if (!allCollections || allCollections.length === 0) {
        DOM.collectionsList.innerHTML = '<div style="padding: 1rem; color: #64748B;">No collections yet.</div>';
        if (DOM.collectionItemsEmpty) DOM.collectionItemsEmpty.classList.remove('hidden');
        return;
      }

      // If active collection is not set or not in list, pick the first
      if (!activeCollectionId || !allCollections.some(c => c.id === activeCollectionId)) {
        activeCollectionId = allCollections[0].id;
      }

      // Render sidebar
      DOM.collectionsList.innerHTML = allCollections.map(col => `
        <button class="collection-nav-item ${col.id === activeCollectionId ? 'active' : ''}" data-col-id="${col.id}">
          <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(col.name)}</span>
          <span class="col-item-count-badge">${col.item_count || 0}</span>
        </button>
      `).join('');

      // Wire sidebar item clicks
      DOM.collectionsList.querySelectorAll('.collection-nav-item').forEach(btn => {
        btn.addEventListener('click', () => {
          activeCollectionId = btn.dataset.colId;
          DOM.collectionsList.querySelectorAll('.collection-nav-item').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          loadActiveCollectionItems();
        });
      });

      loadActiveCollectionItems();
    } catch (err) {
      console.warn('[Kuro] Error loading collections:', err);
    }
  }

  async function loadActiveCollectionItems() {
    const col = allCollections.find(c => c.id === activeCollectionId);
    if (!col) return;

    if (DOM.activeColName) DOM.activeColName.textContent = col.name;
    if (DOM.activeColDesc) DOM.activeColDesc.textContent = col.description || 'Custom personal collection';

    if (!DOM.collectionItemsGrid) return;
    DOM.collectionItemsGrid.innerHTML = '<div style="color: #94A3B8; padding: 2rem;">Loading items...</div>';

    const franchise = DOM.colFilterFranchise ? DOM.colFilterFranchise.value : 'all';
    const resolution = DOM.colFilterRes ? DOM.colFilterRes.value : 'all';
    const search = DOM.colSearchInput ? DOM.colSearchInput.value.trim() : '';

    const params = new URLSearchParams();
    if (franchise && franchise !== 'all') params.append('franchise', franchise);
    if (resolution && resolution !== 'all') params.append('resolution', resolution);
    if (search) params.append('search', search);

    try {
      const res = await fetch(`${STATE.backendBase}/api/collections/${col.id}/items?${params.toString()}`);
      if (!res.ok) throw new Error('Failed to load collection items');
      const items = await res.json();

      if (!items || items.length === 0) {
        DOM.collectionItemsGrid.innerHTML = '';
        if (DOM.collectionItemsEmpty) DOM.collectionItemsEmpty.classList.remove('hidden');
        return;
      }

      if (DOM.collectionItemsEmpty) DOM.collectionItemsEmpty.classList.add('hidden');
      DOM.collectionItemsGrid.innerHTML = items.map(item => renderWallpaperCard(item, 'collection')).join('');
      attachWallpaperCardListeners(DOM.collectionItemsGrid, 'collection');
    } catch (err) {
      DOM.collectionItemsGrid.innerHTML = `<div style="color: #F87171; padding: 2rem;">Error: ${err.message}</div>`;
    }
  }

  // --- TAB 3: BLACKLIST ---
  async function loadBlacklistTab() {
    if (!DOM.blacklistGrid) return;
    DOM.blacklistGrid.innerHTML = '<div style="color: #94A3B8; padding: 2rem;">Loading blacklist...</div>';

    try {
      const res = await fetch(`${STATE.backendBase}/api/blacklist`);
      if (!res.ok) throw new Error('Failed to load blacklist');
      const items = await res.json();

      if (DOM.libTabBlCount) DOM.libTabBlCount.textContent = items.length;

      if (!items || items.length === 0) {
        DOM.blacklistGrid.innerHTML = '';
        if (DOM.blacklistEmpty) DOM.blacklistEmpty.classList.remove('hidden');
        return;
      }

      if (DOM.blacklistEmpty) DOM.blacklistEmpty.classList.add('hidden');
      DOM.blacklistGrid.innerHTML = items.map(item => renderWallpaperCard(item, 'blacklist')).join('');
      attachWallpaperCardListeners(DOM.blacklistGrid, 'blacklist');
    } catch (err) {
      DOM.blacklistGrid.innerHTML = `<div style="color: #F87171; padding: 2rem;">Error: ${err.message}</div>`;
    }
  }

  // --- TAB 4: STATS & STORAGE ---
  async function loadStatsTab() {
    try {
      const res = await fetch(`${STATE.backendBase}/api/library/stats`);
      if (!res.ok) throw new Error('Failed to load library stats');
      const stats = await res.json();

      if (DOM.statLibDisplayed) DOM.statLibDisplayed.textContent = stats.total_displayed || 0;
      if (DOM.statLibFranchises) DOM.statLibFranchises.textContent = stats.franchises_explored || 0;
      if (DOM.statLibFavorites) DOM.statLibFavorites.textContent = stats.total_favorites || 0;
      if (DOM.statLibBlacklisted) DOM.statLibBlacklisted.textContent = stats.total_blacklisted || 0;

      const cacheUtil = stats.cache_utilization || {};
      const storage = stats.storage || {};

      if (DOM.storageCachePercent) DOM.storageCachePercent.textContent = `${cacheUtil.percent || 0}%`;
      if (DOM.storageCacheProgress) DOM.storageCacheProgress.style.width = `${Math.min(cacheUtil.percent || 0, 100)}%`;

      if (DOM.storageFavoritesSize) DOM.storageFavoritesSize.textContent = `${storage.favorites_mb || 0} MB`;
      if (DOM.storageFavoritesFiles) DOM.storageFavoritesFiles.textContent = `(${storage.favorites_files || 0} files)`;

      if (DOM.storageCacheSize) DOM.storageCacheSize.textContent = `${storage.cache_mb || 0} MB`;
      if (DOM.storageCacheFiles) DOM.storageCacheFiles.textContent = `(${storage.cache_files || 0} / 200 files)`;

      if (DOM.storageTotalSize) DOM.storageTotalSize.textContent = `${storage.total_mb || 0} MB`;
      if (DOM.storageTotalGb) DOM.storageTotalGb.textContent = `(${storage.total_gb || 0} GB)`;
    } catch (err) {
      console.warn('[Kuro] Error loading stats tab:', err);
    }
  }

  // Purge prefetch cache
  async function purgePrefetchCache() {
    try {
      const res = await backendPost('/api/cache/purge');
      if (res.ok) {
        const data = await res.json();
        showToast(`Cache purged: removed ${data.purged_count} files 🧹`);
        loadStatsTab();
      }
    } catch (err) {
      showToast('Error purging cache');
    }
  }

  // --- CARD RENDERING & INTERACTIONS ---
  function renderWallpaperCard(item, context = 'favorite') {
    const thumbUrl = item.local_path ? `/${item.local_path}` : (item.id ? `/api/image/${item.id}` : item.url);
    const anime = item.anime || item.mood || 'Anime';
    const character = item.character || 'Artwork';
    const res = item.resolution || 'High Res';

    // Status Badge
    let badgeHtml = '';
    if (context === 'favorite') {
      const status = item.download_status || 'pending';
      if (status === 'completed') {
        const sz = item.file_size ? `${Math.round(item.file_size / (1024 * 1024) * 10) / 10} MB` : 'Saved';
        badgeHtml = `<span class="card-status-badge badge-completed">✓ ${sz}</span>`;
      } else if (status === 'downloading') {
        badgeHtml = `<span class="card-status-badge badge-downloading">⬇ ${item.download_progress || 0}%</span>`;
      } else if (status === 'failed') {
        badgeHtml = `<span class="card-status-badge badge-failed" title="${escapeHtml(item.error_message || '')}">✕ Failed</span>`;
      } else {
        badgeHtml = `<span class="card-status-badge badge-pending">⏳ Queued</span>`;
      }
    } else if (context === 'blacklist') {
      badgeHtml = `<span class="card-status-badge badge-failed">🚫 Excluded</span>`;
    }

    // Buttons
    let actionsHtml = '';
    if (context === 'favorite') {
      actionsHtml = `
        <button class="card-action-btn card-btn-play" data-id="${item.id}" title="Play on Screensaver">▶ Play</button>
        <button class="card-action-btn card-btn-add-col" data-id="${item.id}" title="Add to Custom Collection">+ Col</button>
        <button class="card-action-btn danger card-btn-remove-fav" data-id="${item.id}" title="Remove Favorite">🗑️</button>
      `;
    } else if (context === 'collection') {
      actionsHtml = `
        <button class="card-action-btn card-btn-play" data-id="${item.id}" title="Play on Screensaver">▶ Play</button>
        <button class="card-action-btn danger card-btn-remove-from-col" data-id="${item.id}" title="Remove from this Collection">🗑️ Remove</button>
      `;
    } else if (context === 'blacklist') {
      actionsHtml = `
        <button class="card-action-btn success card-btn-restore-bl" data-id="${item.id}" title="Restore to circulation">🔄 Restore to Rotation</button>
      `;
    }

    return `
      <div class="wallpaper-card" data-card-id="${item.id}" data-url="${escapeHtml(item.url || thumbUrl)}" data-anime="${escapeHtml(anime)}" data-char="${escapeHtml(character)}" data-res="${escapeHtml(res)}">
        <div class="wallpaper-thumb-wrapper">
          <img src="${thumbUrl}" class="wallpaper-thumb-img" loading="lazy" alt="${escapeHtml(anime)}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 60%22><rect width=%22100%22 height=%2260%22 fill=%22%230A0F18%22/><text x=%2250%22 y=%2232%22 fill=%22%234B5563%22 font-size=%228%22 text-anchor=%22middle%22>Preview</text></svg>'"/>
          ${badgeHtml}
          <div class="card-meta-overlay">
            <span class="card-res-pill">${res}</span>
          </div>
        </div>
        <div class="wallpaper-card-info">
          <span class="card-franchise-name" title="${escapeHtml(anime)}">${escapeHtml(anime)}</span>
          <span class="card-character-name" title="${escapeHtml(character)}">${escapeHtml(character)}</span>
          ${context === 'blacklist' && item.reason ? `<span class="card-blacklist-reason">${escapeHtml(item.reason)}</span>` : ''}
          <div class="card-actions-row">
            ${actionsHtml}
          </div>
        </div>
      </div>
    `;
  }

  function attachWallpaperCardListeners(container, context) {
    if (!container) return;

    // Play button
    container.querySelectorAll('.card-btn-play').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const card = btn.closest('.wallpaper-card');
        const id = card.dataset.cardId;
        const url = card.dataset.url;
        const anime = card.dataset.anime;
        const character = card.dataset.char;
        const resolution = card.dataset.res;

        closeLibraryModal();
        displaySpecificWallpaper({ id, url, anime, character, resolution, level: 2 });
      });
    });

    // Add to collection button
    container.querySelectorAll('.card-btn-add-col').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        openAddToCollectionModal(btn.dataset.id);
      });
    });

    // Remove favorite
    container.querySelectorAll('.card-btn-remove-fav').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = btn.dataset.id;
        try {
          await backendPost('/api/favorite/remove', { id });
          showToast('Favorite removed');
          const idx = STATE.favorites.findIndex(f => f.id === id);
          if (idx >= 0) STATE.favorites.splice(idx, 1);
          localStorage.setItem('kuro_favorites', JSON.stringify(STATE.favorites));
          loadFavoritesTab();
        } catch (err) {
          showToast('Error removing favorite');
        }
      });
    });

    // Remove from collection
    container.querySelectorAll('.card-btn-remove-from-col').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = btn.dataset.id;
        if (!activeCollectionId) return;
        try {
          await backendPost('/api/collections/remove-item', { collection_id: activeCollectionId, wallpaper_id: id });
          showToast('Removed from collection');
          loadActiveCollectionItems();
          // Update collection count
          loadCollectionsTab();
        } catch (err) {
          showToast('Error removing from collection');
        }
      });
    });

    // Restore from blacklist
    container.querySelectorAll('.card-btn-restore-bl').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = btn.dataset.id;
        try {
          await backendPost('/api/blacklist/restore', { id });
          showToast('Restored artwork to rotation 🔄');
          loadBlacklistTab();
        } catch (err) {
          showToast('Error restoring artwork');
        }
      });
    });
  }

  // --- BLACKLIST ACTIVE WALLPAPER ---
  async function blacklistCurrentWallpaper() {
    if (!STATE.currentWallpaper) return;
    const wp = STATE.currentWallpaper;
    const reason = 'User excluded from screensaver';
    try {
      await backendPost('/api/blacklist', { id: wp.id, reason });
      showToast('Artwork blacklisted forever 🚫');
      displayNextWallpaper();
    } catch (err) {
      showToast('Failed to blacklist artwork');
    }
  }

  // --- COLLECTION PROMPT & PICKER DIALOGS ---
  function openPromptModal(action = 'create') {
    promptAction = action;
    if (!DOM.collectionPromptModal) return;
    DOM.collectionPromptModal.classList.remove('hidden');

    if (action === 'create') {
      DOM.promptModalTitle.textContent = '✨ New Collection';
      DOM.promptInputName.value = '';
      DOM.promptInputDesc.value = '';
    } else {
      DOM.promptModalTitle.textContent = '✏️ Rename Collection';
      const col = allCollections.find(c => c.id === activeCollectionId);
      DOM.promptInputName.value = col ? col.name : '';
      DOM.promptInputDesc.value = col ? col.description || '' : '';
    }
    DOM.promptInputName.focus();
  }

  async function submitPromptModal() {
    const name = DOM.promptInputName.value.trim();
    const desc = DOM.promptInputDesc.value.trim();
    if (!name) {
      showToast('Collection name is required');
      return;
    }

    try {
      if (promptAction === 'create') {
        const res = await backendPost('/api/collections', { name, description: desc });
        if (res.ok) {
          const newCol = await res.json();
          activeCollectionId = newCol.id;
          showToast(`Collection "${name}" created!`);
          DOM.collectionPromptModal.classList.add('hidden');
          loadCollectionsTab();
        } else {
          showToast('Collection name already exists');
        }
      } else {
        if (!activeCollectionId) return;
        const res = await backendPost('/api/collections/rename', { id: activeCollectionId, name, description: desc });
        if (res.ok) {
          showToast(`Collection updated!`);
          DOM.collectionPromptModal.classList.add('hidden');
          loadCollectionsTab();
        }
      }
    } catch (err) {
      showToast('Error saving collection');
    }
  }

  async function deleteActiveCollection() {
    if (!activeCollectionId) return;
    const col = allCollections.find(c => c.id === activeCollectionId);
    if (!col) return;
    if (!confirm(`Delete collection "${col.name}"? Wallpapers will remain in your library.`)) return;

    try {
      await backendPost('/api/collections/delete', { id: activeCollectionId });
      showToast(`Collection "${col.name}" deleted.`);
      activeCollectionId = null;
      loadCollectionsTab();
    } catch (err) {
      showToast('Error deleting collection');
    }
  }

  function openAddToCollectionModal(wallpaperId) {
    targetWallpaperForCollection = wallpaperId;
    if (!DOM.addToCollectionModal) return;
    DOM.addToCollectionModal.classList.remove('hidden');
    if (DOM.addColWpid) DOM.addColWpid.textContent = wallpaperId;

    if (!DOM.addColPickerList) return;
    if (!allCollections || allCollections.length === 0) {
      DOM.addColPickerList.innerHTML = '<div style="color: #64748B; padding: 1rem;">No collections created yet.</div>';
      return;
    }

    DOM.addColPickerList.innerHTML = allCollections.map(col => `
      <div class="collection-picker-item" data-col-id="${col.id}">
        <span>${escapeHtml(col.name)}</span>
        <span class="col-item-count-badge">${col.item_count || 0}</span>
      </div>
    `).join('');

    DOM.addColPickerList.querySelectorAll('.collection-picker-item').forEach(item => {
      item.addEventListener('click', async () => {
        const colId = item.dataset.colId;
        try {
          await backendPost('/api/collections/add-item', { collection_id: colId, wallpaper_id: targetWallpaperForCollection });
          showToast(`Added to collection! ✨`);
          DOM.addToCollectionModal.classList.add('hidden');
          if (currentLibraryTab === 'collections') loadCollectionsTab();
        } catch (err) {
          showToast('Error adding to collection');
        }
      });
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function debounce(fn, ms) {
    let timer = null;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  async function displaySpecificWallpaper(wallpaper) {
    if (!wallpaper || STATE.isTransitioning) return;
    STATE.isTransitioning = true;
    clearTimeout(STATE.timer);
    cancelAnimationFrame(STATE.progressRaf);

    try {
      const preloadedImg = await preloadImage(wallpaper.url);
      wallpaper._preloadedImg = preloadedImg;
      await applyWallpaper(wallpaper);
      STATE.sessionHistory.push(wallpaper);
      STATE.sessionHistoryIndex = STATE.sessionHistory.length - 1;
      showToast(`Displaying ${wallpaper.anime || 'Anime Art'}`);
    } catch (err) {
      showToast('Failed to load artwork image');
    } finally {
      STATE.isTransitioning = false;
      startSlideTimer();
    }
  }

  // --- EXIT & SYSTEM SHUTDOWN ---
  async function exitScreensaverCleanly() {
    if (!confirm('Exit KuroAnime Screensaver and stop the background server?')) return;
    showToast('Shutting down KuroAnime Screensaver... Goodbye.');
    stopSoundscapeAudio();

    try {
      await backendPost('/api/shutdown', {});
    } catch (_) {}

    setTimeout(() => {
      window.close();
      // In case window.close() is blocked by browser policy
      document.body.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;background:#05070A;color:#CBD5E1;font-family:sans-serif;text-align:center;">
          <h2 style="color:#6EE7B7;margin-bottom:0.5rem;">KuroAnime Screensaver Stopped Cleanly</h2>
          <p style="color:#94A3B8;max-width:400px;line-height:1.5;">The Python server and database have been safely checkpointed and terminated. You can now close this browser tab.</p>
        </div>
      `;
    }, 600);
  }

  async function loadLauncherConfig() {
    try {
      const res = await fetch(`${STATE.backendBase}/api/launcher/config`);
      if (res.ok) {
        const cfg = await res.json();
        if (DOM.settingWinStartup) DOM.settingWinStartup.checked = !!cfg.autostart_on_boot;
        if (DOM.settingLaunchMode && cfg.mode) DOM.settingLaunchMode.value = cfg.mode;
      }
    } catch (_) {}
  }

  async function loadPersonalizationProfile() {
    try {
      const res = await fetch(`${STATE.backendBase}/api/recommendations/profile`, { signal: AbortSignal.timeout(3000) });
      if (!res.ok) return;
      const data = await res.json();

      if (DOM.settingRecEnabled) {
        DOM.settingRecEnabled.checked = !!data.enabled;
        if (DOM.recSubcontrols) {
          DOM.recSubcontrols.style.opacity = data.enabled ? '1' : '0.4';
          DOM.recSubcontrols.style.pointerEvents = data.enabled ? 'auto' : 'none';
        }
      }

      if (DOM.settingRecDiversity) {
        DOM.settingRecDiversity.checked = !!data.diversity_penalty;
      }

      if (DOM.recEventsBadge) {
        DOM.recEventsBadge.textContent = `${data.events_count || 0} Interactions`;
      }

      // Populate top franchises chips
      if (DOM.recFranchiseChips) {
        if (!data.franchises || data.franchises.length === 0) {
          DOM.recFranchiseChips.innerHTML = '<span style="font-size: 0.75rem; color: #94A3B8;">No interaction history yet. Browse or favorite art to train!</span>';
        } else {
          DOM.recFranchiseChips.innerHTML = data.franchises.map(f => {
            const scoreClass = f.total_score >= 0 ? 'positive' : 'negative';
            const sign = f.total_score >= 0 ? '+' : '';
            return `<div class="rec-chip ${scoreClass}" title="Learned: ${f.learned_score.toFixed(1)}, Manual: ${f.manual_score.toFixed(1)}, Events: ${f.events_count}">
              <span>${escapeHtml(f.name)}</span>
              <span class="rec-chip-score">${sign}${f.total_score.toFixed(1)}</span>
            </div>`;
          }).join('');
        }
      }

      // Populate top characters chips
      if (DOM.recCharacterChips) {
        if (!data.characters || data.characters.length === 0) {
          DOM.recCharacterChips.innerHTML = '<span style="font-size: 0.75rem; color: #94A3B8;">No character preferences recorded yet.</span>';
        } else {
          DOM.recCharacterChips.innerHTML = data.characters.map(c => {
            const scoreClass = c.total_score >= 0 ? 'positive' : 'negative';
            const sign = c.total_score >= 0 ? '+' : '';
            return `<div class="rec-chip ${scoreClass}" title="Learned: ${c.learned_score.toFixed(1)}, Manual: ${c.manual_score.toFixed(1)}, Events: ${c.events_count}">
              <span>${escapeHtml(c.name)}</span>
              <span class="rec-chip-score">${sign}${c.total_score.toFixed(1)}</span>
            </div>`;
          }).join('');
        }
      }

      // Populate manual franchise adjustment dropdown
      if (DOM.recManualFranchiseSelect) {
        const currentVal = DOM.recManualFranchiseSelect.value;
        const franchiseNames = new Set();
        if (Array.isArray(STATE.franchisesList)) {
          STATE.franchisesList.forEach(f => franchiseNames.add(f.name || f.slug));
        }
        if (Array.isArray(data.franchises)) {
          data.franchises.forEach(f => franchiseNames.add(f.name));
        }
        const sorted = Array.from(franchiseNames).sort();
        DOM.recManualFranchiseSelect.innerHTML = '<option value="">Select franchise to adjust...</option>' +
          sorted.map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join('');
        if (currentVal) DOM.recManualFranchiseSelect.value = currentVal;
      }

      // Stats breakdown
      if (data.stats) {
        if (DOM.recStatDwell) DOM.recStatDwell.textContent = data.stats.dwell_sessions || 0;
        if (DOM.recStatSkips) DOM.recStatSkips.textContent = data.stats.skips || 0;
        if (DOM.recStatRevisits) DOM.recStatRevisits.textContent = data.stats.revisits || 0;
      }
    } catch (err) {
      console.warn('[Kuro] Failed to load personalization profile:', err);
    }
  }

  window.addEventListener('beforeunload', () => {
    recordDwellForCurrentWallpaper(false);
  });

  async function loadQualitySettings() {
    try {
      const res = await fetch(`${STATE.backendBase}/api/quality/settings`, { signal: AbortSignal.timeout(3000) });
      if (res.ok) {
        const cfg = await res.json();
        if (DOM.settingQualityThreshold) {
          DOM.settingQualityThreshold.value = cfg.min_quality_score != null ? cfg.min_quality_score : 50;
          if (DOM.settingQualityThresholdLabel) {
            DOM.settingQualityThresholdLabel.textContent = `${DOM.settingQualityThreshold.value} / 100`;
          }
        }
        if (DOM.settingQualityNativeRes) DOM.settingQualityNativeRes.checked = !!cfg.prefer_native_res;
        if (DOM.settingQualityAspectRatio) DOM.settingQualityAspectRatio.checked = !!cfg.prefer_aspect_ratio;
        if (DOM.settingQualityAvoidBright) DOM.settingQualityAvoidBright.checked = !!cfg.avoid_too_bright;
        if (DOM.settingQualityAvoidDark) DOM.settingQualityAvoidDark.checked = !!cfg.avoid_too_dark;
        if (DOM.settingQualityPopWeight) DOM.settingQualityPopWeight.value = String(cfg.popularity_weight != null ? cfg.popularity_weight : 0.35);
      }

      const scoreRes = await fetch(`${STATE.backendBase}/api/quality/scores`, { signal: AbortSignal.timeout(3000) });
      if (scoreRes.ok) {
        const summary = await scoreRes.json();
        if (DOM.qualityAvgBadge && summary.avg_quality) {
          DOM.qualityAvgBadge.textContent = `Avg: ${summary.avg_quality}/100`;
        }
      }
    } catch (err) {
      console.warn('[Kuro] Failed to load quality settings:', err);
    }
  }

  async function updateQualitySettingsFromUI() {
    const popWeight = DOM.settingQualityPopWeight ? parseFloat(DOM.settingQualityPopWeight.value) : 0.35;
    const payload = {
      min_quality_score: DOM.settingQualityThreshold ? parseFloat(DOM.settingQualityThreshold.value) : 50.0,
      prefer_native_res: DOM.settingQualityNativeRes ? (DOM.settingQualityNativeRes.checked ? 1 : 0) : 1,
      prefer_aspect_ratio: DOM.settingQualityAspectRatio ? (DOM.settingQualityAspectRatio.checked ? 1 : 0) : 1,
      avoid_too_bright: DOM.settingQualityAvoidBright ? (DOM.settingQualityAvoidBright.checked ? 1 : 0) : 1,
      avoid_too_dark: DOM.settingQualityAvoidDark ? (DOM.settingQualityAvoidDark.checked ? 1 : 0) : 0,
      popularity_weight: popWeight,
      technical_weight: parseFloat((1.0 - popWeight).toFixed(2))
    };

    try {
      await backendPost('/api/quality/settings', payload);
      showToast('Quality scoring criteria updated');
    } catch (err) {
      console.warn('[Kuro] Error saving quality settings:', err);
    }
  }

  async function rescoreQualityCatalog() {
    try {
      showToast('Re-evaluating catalog quality scores...');
      const res = await backendPost('/api/quality/rescore', {});
      if (res.ok) {
        const data = await res.json();
        showToast(`Catalog evaluated (${data.summary ? data.summary.scored_wallpapers : 0} artworks)`);
        await loadQualitySettings();
      }
    } catch (err) {
      showToast('Failed to re-score catalog');
    }
  }

  // --- INTELLIGENT SLIDESHOW SCHEDULING MANAGEMENT ---
  function updateSchedulerSubpanels(strategy) {
    if (!DOM.panelFixedInterval) return;
    DOM.panelFixedInterval.classList.toggle('hidden', strategy === 'random' || strategy === 'manual');
    if (DOM.panelRandomInterval) DOM.panelRandomInterval.classList.toggle('hidden', strategy !== 'random');
    if (DOM.panelTimeSlots) DOM.panelTimeSlots.classList.toggle('hidden', strategy !== 'time_of_day');
    if (DOM.panelFranchiseRotation) DOM.panelFranchiseRotation.classList.toggle('hidden', strategy !== 'franchise_rotation');
  }

  async function loadSchedulerSettings() {
    try {
      const res = await fetch(`${STATE.backendBase}/api/scheduler/settings`, { signal: AbortSignal.timeout(3000) });
      if (res.ok) {
        const cfg = await res.json();
        STATE.schedulerStrategy = cfg.strategy || STATE.schedulerStrategy || 'fixed';
        STATE.schedulerFixedSec = cfg.fixed_seconds || STATE.schedulerFixedSec || 30;
        STATE.intervalSeconds = STATE.schedulerFixedSec;
        STATE.schedulerRandMin = cfg.random_min || STATE.schedulerRandMin || 15;
        STATE.schedulerRandMax = cfg.random_max || STATE.schedulerRandMax || 60;
        STATE.schedulerDaySec = cfg.day_seconds || STATE.schedulerDaySec || 25;
        STATE.schedulerEveSec = cfg.evening_seconds || STATE.schedulerEveSec || 35;
        STATE.schedulerNightSec = cfg.night_seconds || STATE.schedulerNightSec || 60;
        STATE.schedulerCinematicSec = cfg.cinematic_seconds || STATE.schedulerCinematicSec || 45;
        STATE.schedulerDashboardSec = cfg.dashboard_seconds || STATE.schedulerDashboardSec || 20;
        STATE.schedulerQualityBonus = cfg.quality_bonus_enabled !== undefined ? !!cfg.quality_bonus_enabled : true;
        STATE.pauseOnHidden = cfg.pause_on_hidden !== undefined ? !!cfg.pause_on_hidden : true;
        STATE.franchiseRotationInterval = cfg.franchise_rotation_interval || STATE.franchiseRotationInterval || 5;

        // Sync to localStorage
        localStorage.setItem('kuro_scheduler_strategy', STATE.schedulerStrategy);
        localStorage.setItem('kuro_scheduler_fixed_sec', STATE.schedulerFixedSec);
        localStorage.setItem('kuro_interval', STATE.schedulerFixedSec);
        localStorage.setItem('kuro_scheduler_rand_min', STATE.schedulerRandMin);
        localStorage.setItem('kuro_scheduler_rand_max', STATE.schedulerRandMax);
        localStorage.setItem('kuro_scheduler_day_sec', STATE.schedulerDaySec);
        localStorage.setItem('kuro_scheduler_eve_sec', STATE.schedulerEveSec);
        localStorage.setItem('kuro_scheduler_night_sec', STATE.schedulerNightSec);
        localStorage.setItem('kuro_scheduler_cinematic_sec', STATE.schedulerCinematicSec);
        localStorage.setItem('kuro_scheduler_dashboard_sec', STATE.schedulerDashboardSec);
        localStorage.setItem('kuro_scheduler_quality_bonus', STATE.schedulerQualityBonus);
        localStorage.setItem('kuro_scheduler_pause_hidden', STATE.pauseOnHidden);
        localStorage.setItem('kuro_scheduler_franchise_rot_interval', STATE.franchiseRotationInterval);
      }
    } catch (e) {
      console.warn('[Kuro] Using local cached scheduler settings:', e);
    }

    applySchedulerPreferencesToUI();
  }

  function applySchedulerPreferencesToUI() {
    if (DOM.settingScheduleStrategy) DOM.settingScheduleStrategy.value = STATE.schedulerStrategy;
    updateSchedulerSubpanels(STATE.schedulerStrategy);

    if (DOM.settingInterval) {
      DOM.settingInterval.value = STATE.schedulerFixedSec;
      if (DOM.settingIntervalLabel) DOM.settingIntervalLabel.textContent = `${STATE.schedulerFixedSec}s`;
    }
    if (DOM.settingRandomMin) {
      DOM.settingRandomMin.value = STATE.schedulerRandMin;
      if (DOM.settingRandomMinLabel) DOM.settingRandomMinLabel.textContent = `${STATE.schedulerRandMin}s`;
    }
    if (DOM.settingRandomMax) {
      DOM.settingRandomMax.value = STATE.schedulerRandMax;
      if (DOM.settingRandomMaxLabel) DOM.settingRandomMaxLabel.textContent = `${STATE.schedulerRandMax}s`;
    }
    if (DOM.settingDaySec) DOM.settingDaySec.value = STATE.schedulerDaySec;
    if (DOM.settingEveSec) DOM.settingEveSec.value = STATE.schedulerEveSec;
    if (DOM.settingNightSec) DOM.settingNightSec.value = STATE.schedulerNightSec;
    if (DOM.settingCinematicSec) {
      DOM.settingCinematicSec.value = STATE.schedulerCinematicSec;
      if (DOM.settingCinematicSecLabel) DOM.settingCinematicSecLabel.textContent = `${STATE.schedulerCinematicSec}s`;
    }
    if (DOM.settingDashboardSec) {
      DOM.settingDashboardSec.value = STATE.schedulerDashboardSec;
      if (DOM.settingDashboardSecLabel) DOM.settingDashboardSecLabel.textContent = `${STATE.schedulerDashboardSec}s`;
    }
    if (DOM.settingFranchiseRotInterval) {
      DOM.settingFranchiseRotInterval.value = STATE.franchiseRotationInterval;
      if (DOM.settingFranchiseRotLabel) DOM.settingFranchiseRotLabel.textContent = `${STATE.franchiseRotationInterval} slides`;
    }
    if (DOM.settingScheduleQualityBonus) DOM.settingScheduleQualityBonus.checked = STATE.schedulerQualityBonus;
    if (DOM.settingSchedulePauseHidden) DOM.settingSchedulePauseHidden.checked = STATE.pauseOnHidden;
  }

  let schedulerDebounceTimer = null;
  function updateSchedulerSettingsFromUI() {
    if (DOM.settingScheduleStrategy) STATE.schedulerStrategy = DOM.settingScheduleStrategy.value;
    if (DOM.settingInterval) {
      STATE.schedulerFixedSec = parseInt(DOM.settingInterval.value, 10);
      STATE.intervalSeconds = STATE.schedulerFixedSec;
    }
    if (DOM.settingRandomMin) STATE.schedulerRandMin = parseInt(DOM.settingRandomMin.value, 10);
    if (DOM.settingRandomMax) {
      STATE.schedulerRandMax = Math.max(STATE.schedulerRandMin, parseInt(DOM.settingRandomMax.value, 10));
      DOM.settingRandomMax.value = STATE.schedulerRandMax;
    }
    if (DOM.settingDaySec) STATE.schedulerDaySec = parseInt(DOM.settingDaySec.value, 10);
    if (DOM.settingEveSec) STATE.schedulerEveSec = parseInt(DOM.settingEveSec.value, 10);
    if (DOM.settingNightSec) STATE.schedulerNightSec = parseInt(DOM.settingNightSec.value, 10);
    if (DOM.settingCinematicSec) STATE.schedulerCinematicSec = parseInt(DOM.settingCinematicSec.value, 10);
    if (DOM.settingDashboardSec) STATE.schedulerDashboardSec = parseInt(DOM.settingDashboardSec.value, 10);
    if (DOM.settingFranchiseRotInterval) STATE.franchiseRotationInterval = parseInt(DOM.settingFranchiseRotInterval.value, 10);
    if (DOM.settingScheduleQualityBonus) STATE.schedulerQualityBonus = DOM.settingScheduleQualityBonus.checked;
    if (DOM.settingSchedulePauseHidden) STATE.pauseOnHidden = DOM.settingSchedulePauseHidden.checked;

    // Update localStorage
    localStorage.setItem('kuro_scheduler_strategy', STATE.schedulerStrategy);
    localStorage.setItem('kuro_scheduler_fixed_sec', STATE.schedulerFixedSec);
    localStorage.setItem('kuro_interval', STATE.schedulerFixedSec);
    localStorage.setItem('kuro_scheduler_rand_min', STATE.schedulerRandMin);
    localStorage.setItem('kuro_scheduler_rand_max', STATE.schedulerRandMax);
    localStorage.setItem('kuro_scheduler_day_sec', STATE.schedulerDaySec);
    localStorage.setItem('kuro_scheduler_eve_sec', STATE.schedulerEveSec);
    localStorage.setItem('kuro_scheduler_night_sec', STATE.schedulerNightSec);
    localStorage.setItem('kuro_scheduler_cinematic_sec', STATE.schedulerCinematicSec);
    localStorage.setItem('kuro_scheduler_dashboard_sec', STATE.schedulerDashboardSec);
    localStorage.setItem('kuro_scheduler_quality_bonus', STATE.schedulerQualityBonus);
    localStorage.setItem('kuro_scheduler_pause_hidden', STATE.pauseOnHidden);
    localStorage.setItem('kuro_scheduler_franchise_rot_interval', STATE.franchiseRotationInterval);

    updateSchedulerSubpanels(STATE.schedulerStrategy);

    // Debounced persist to SQLite backend
    clearTimeout(schedulerDebounceTimer);
    schedulerDebounceTimer = setTimeout(async () => {
      const payload = {
        strategy: STATE.schedulerStrategy,
        fixed_seconds: STATE.schedulerFixedSec,
        random_min: STATE.schedulerRandMin,
        random_max: STATE.schedulerRandMax,
        day_seconds: STATE.schedulerDaySec,
        evening_seconds: STATE.schedulerEveSec,
        night_seconds: STATE.schedulerNightSec,
        cinematic_seconds: STATE.schedulerCinematicSec,
        dashboard_seconds: STATE.schedulerDashboardSec,
        quality_bonus_enabled: STATE.schedulerQualityBonus ? 1 : 0,
        pause_on_hidden: STATE.pauseOnHidden ? 1 : 0,
        franchise_rotation_interval: STATE.franchiseRotationInterval
      };
      try {
        await backendPost('/api/scheduler/settings', payload);
      } catch (err) {
        console.warn('[Kuro] Error persisting scheduler settings:', err);
      }
    }, 400);

    // If active wallpaper is showing and not transitioning, restart slide timer with new schedule
    if (!STATE.isTransitioning && !STATE.isPaused) {
      startSlideTimer();
    }
  }

  // =========================================================================
  // AMBIENT SOUNDSCAPE ENGINE (OPTIONAL & LOCAL AUDIO)
  // =========================================================================

  const DEFAULT_SOUNDSCAPES = [
    { id: 'rain', name: 'Rain', description: 'Gentle rhythmic rainfall & droplets' },
    { id: 'thunderstorm', name: 'Thunderstorm', description: 'Rolling thunder & storm' },
    { id: 'japanese_forest', name: 'Japanese Forest', description: 'Bamboo rustle & wind chimes' },
    { id: 'night_city', name: 'Night City Ambience', description: 'Metropolitan hum & drone' },
    { id: 'ocean_waves', name: 'Ocean Waves', description: 'Rolling surf & coastal swells' },
    { id: 'wind', name: 'Wind', description: 'Mountain gusts & breezes' },
    { id: 'fireplace', name: 'Fireplace', description: 'Warm hearth & crackling embers' },
    { id: 'space_ambience', name: 'Space Ambience', description: 'Deep celestial cosmic drone' }
  ];

  function initSoundscapeAudio() {
    STATE.audioChannelA = new Audio();
    STATE.audioChannelB = new Audio();

    [STATE.audioChannelA, STATE.audioChannelB].forEach(ch => {
      ch.loop = true;
      ch.volume = 0.0;
      ch.muted = STATE.soundscapeMuted;
      ch.preload = 'auto';
    });

    updateSoundscapeHudIcon();
  }

  function getSoundscapeTrackUrl(trackId) {
    if (Array.isArray(STATE.soundscapeCatalog)) {
      const found = STATE.soundscapeCatalog.find(t => t.id === trackId);
      if (found && found.filename) {
        return `/soundscapes/${found.filename}`;
      }
    }
    return `/soundscapes/${trackId}.wav`;
  }

  function getSoundscapeTrackName(trackId) {
    if (Array.isArray(STATE.soundscapeCatalog)) {
      const found = STATE.soundscapeCatalog.find(t => t.id === trackId);
      if (found && found.name) return found.name;
    }
    const def = DEFAULT_SOUNDSCAPES.find(t => t.id === trackId);
    return def ? def.name : trackId.replace('_', ' ').toUpperCase();
  }

  function updateSoundscapeHudIcon() {
    if (!DOM.btnSoundscapeToggle) return;
    if (!STATE.soundscapeEnabled || STATE.soundscapeMuted) {
      DOM.btnSoundscapeToggle.textContent = '🔇';
      DOM.btnSoundscapeToggle.title = 'Ambient Soundscape (Muted - Press A to Unmute)';
      DOM.btnSoundscapeToggle.classList.remove('active');
    } else {
      DOM.btnSoundscapeToggle.textContent = '🔊';
      DOM.btnSoundscapeToggle.title = `Ambient Soundscape: ${getSoundscapeTrackName(STATE.soundscapeTrack)} (${STATE.soundscapeVolume}% - Press A to Mute)`;
      DOM.btnSoundscapeToggle.classList.add('active');
    }

    if (DOM.btnSoundscapeMute) {
      DOM.btnSoundscapeMute.textContent = STATE.soundscapeMuted ? 'Muted 🔇' : 'Active 🔊';
      DOM.btnSoundscapeMute.style.color = STATE.soundscapeMuted ? 'var(--text-dim)' : '#34D399';
    }
  }

  function playOrCrossfadeSoundscape(newTrackId, forceRestart = false) {
    if (!STATE.audioChannelA || !STATE.audioChannelB) {
      initSoundscapeAudio();
    }

    if (!STATE.soundscapeEnabled) {
      stopSoundscapeAudio();
      return;
    }

    STATE.soundscapeTrack = newTrackId;
    localStorage.setItem('kuro_soundscape_track', newTrackId);
    if (DOM.settingSoundscapeTrack) DOM.settingSoundscapeTrack.value = newTrackId;

    const targetUrl = getSoundscapeTrackUrl(newTrackId);
    const targetVolume = STATE.soundscapeMuted ? 0.0 : Math.max(0.0, Math.min(1.0, STATE.soundscapeVolume / 100.0));

    // Choose incoming and outgoing audio channels
    const isChannelA = STATE.activeAudioChannel === 'a';
    const outgoing = isChannelA ? STATE.audioChannelA : STATE.audioChannelB;
    const incoming = isChannelA ? STATE.audioChannelB : STATE.audioChannelA;
    const incomingName = isChannelA ? 'b' : 'a';

    // Clear any active crossfade ticker
    if (STATE.soundscapeCrossfadeTimer) {
      clearInterval(STATE.soundscapeCrossfadeTimer);
      STATE.soundscapeCrossfadeTimer = null;
    }

    // Set up incoming channel
    incoming.src = targetUrl;
    incoming.loop = true;
    incoming.volume = 0.0;
    incoming.muted = STATE.soundscapeMuted;

    // Start playing incoming
    const playPromise = incoming.play();
    if (playPromise !== undefined) {
      playPromise.catch(() => {
        console.log('[KuroSound] Auto-playback waiting for user gesture.');
      });
    }

    // Smooth Crossfade Ramp (equal-power / linear interpolation)
    const crossfadeDurationMs = Math.max(500, (STATE.soundscapeCrossfade || 2.5) * 1000);
    const stepIntervalMs = 25;
    const totalSteps = Math.floor(crossfadeDurationMs / stepIntervalMs);
    let step = 0;
    const outgoingStartVol = outgoing.volume || 0.0;

    STATE.soundscapeCrossfadeTimer = setInterval(() => {
      step++;
      const progress = Math.min(1.0, step / totalSteps);

      // Outgoing ramps down to 0
      outgoing.volume = Math.max(0.0, outgoingStartVol * (1.0 - progress));
      // Incoming ramps up to targetVolume
      if (!STATE.soundscapeMuted) {
        incoming.volume = Math.max(0.0, Math.min(1.0, targetVolume * progress));
      }

      if (progress >= 1.0) {
        clearInterval(STATE.soundscapeCrossfadeTimer);
        STATE.soundscapeCrossfadeTimer = null;
        outgoing.pause();
        outgoing.volume = 0.0;
        incoming.volume = targetVolume;
        STATE.activeAudioChannel = incomingName;
        updateSoundscapeHudIcon();
      }
    }, stepIntervalMs);

    updateSoundscapeHudIcon();
  }

  function toggleSoundscapeMute() {
    // If soundscape is not enabled yet, pressing mute toggle enables it and un-mutes
    if (!STATE.soundscapeEnabled) {
      STATE.soundscapeEnabled = true;
      STATE.soundscapeMuted = false;
      localStorage.setItem('kuro_soundscape_enabled', 'true');
      localStorage.setItem('kuro_soundscape_muted', 'false');
      if (DOM.settingSoundscapeEnabled) DOM.settingSoundscapeEnabled.checked = true;
      if (DOM.soundscapeSubcontrols) DOM.soundscapeSubcontrols.classList.remove('disabled');
      playOrCrossfadeSoundscape(STATE.soundscapeTrack);
      showToast(`Soundscape ON: ${getSoundscapeTrackName(STATE.soundscapeTrack)} (Volume: ${STATE.soundscapeVolume}%) 🔊`);
      saveSoundscapeSettingsToBackend();
      return;
    }

    STATE.soundscapeMuted = !STATE.soundscapeMuted;
    localStorage.setItem('kuro_soundscape_muted', String(STATE.soundscapeMuted));

    if (STATE.audioChannelA) STATE.audioChannelA.muted = STATE.soundscapeMuted;
    if (STATE.audioChannelB) STATE.audioChannelB.muted = STATE.soundscapeMuted;

    const activeCh = STATE.activeAudioChannel === 'b' ? STATE.audioChannelB : STATE.audioChannelA;
    if (activeCh) {
      if (STATE.soundscapeMuted) {
        activeCh.volume = 0.0;
        showToast('Soundscape Muted 🔇');
      } else {
        const targetVol = Math.max(0.0, Math.min(1.0, STATE.soundscapeVolume / 100.0));
        activeCh.volume = targetVol;
        if (activeCh.paused) {
          activeCh.play().catch(() => {});
        }
        showToast(`Soundscape: ${getSoundscapeTrackName(STATE.soundscapeTrack)} (${STATE.soundscapeVolume}%) 🔊`);
      }
    }

    updateSoundscapeHudIcon();
    saveSoundscapeSettingsToBackend();
  }


  function setSoundscapeVolume(vol) {
    const clamped = Math.max(0, Math.min(100, vol));
    STATE.soundscapeVolume = clamped;
    localStorage.setItem('kuro_soundscape_volume', clamped);

    if (DOM.settingSoundscapeVolume) DOM.settingSoundscapeVolume.value = clamped;
    if (DOM.settingSoundscapeVolLabel) DOM.settingSoundscapeVolLabel.textContent = `${clamped}%`;

    const activeCh = STATE.activeAudioChannel === 'b' ? STATE.audioChannelB : STATE.audioChannelA;
    if (activeCh && !STATE.soundscapeMuted && STATE.soundscapeEnabled) {
      activeCh.volume = clamped / 100.0;
    }

    updateSoundscapeHudIcon();
    saveSoundscapeSettingsToBackend();
  }


  function cycleSoundscapeTrack(forward = true) {
    const tracks = (Array.isArray(STATE.soundscapeCatalog) && STATE.soundscapeCatalog.length > 0)
      ? STATE.soundscapeCatalog
      : DEFAULT_SOUNDSCAPES;

    const currentIdx = tracks.findIndex(t => t.id === STATE.soundscapeTrack);
    let nextIdx = 0;
    if (currentIdx !== -1) {
      if (forward) {
        nextIdx = (currentIdx + 1) % tracks.length;
      } else {
        nextIdx = (currentIdx - 1 + tracks.length) % tracks.length;
      }
    }

    const nextTrack = tracks[nextIdx];
    if (nextTrack) {
      if (!STATE.soundscapeEnabled) {
        STATE.soundscapeEnabled = true;
        STATE.soundscapeMuted = false;
        if (DOM.settingSoundscapeEnabled) DOM.settingSoundscapeEnabled.checked = true;
        if (DOM.soundscapeSubcontrols) DOM.soundscapeSubcontrols.classList.remove('disabled');
      }
      playOrCrossfadeSoundscape(nextTrack.id);
      showToast(`🎵 Soundscape: ${nextTrack.name}`);
      saveSoundscapeSettingsToBackend();
    }
  }

  function stopSoundscapeAudio() {
    if (STATE.soundscapeCrossfadeTimer) {
      clearInterval(STATE.soundscapeCrossfadeTimer);
      STATE.soundscapeCrossfadeTimer = null;
    }
    if (STATE.audioChannelA) {
      STATE.audioChannelA.pause();
      STATE.audioChannelA.currentTime = 0;
    }
    if (STATE.audioChannelB) {
      STATE.audioChannelB.pause();
      STATE.audioChannelB.currentTime = 0;
    }
    updateSoundscapeHudIcon();
  }

  async function loadSoundscapeSettings() {
    try {
      // 1. Fetch available soundscape catalog
      const catRes = await fetch(`${STATE.backendBase}/api/soundscapes`, { signal: AbortSignal.timeout(3000) });
      if (catRes.ok) {
        const catData = await catRes.json();
        if (Array.isArray(catData.soundscapes)) {
          STATE.soundscapeCatalog = catData.soundscapes;
          populateSoundscapeDropdown(catData.soundscapes);
        }
      }

      // 2. Fetch user soundscape preferences
      const setRes = await fetch(`${STATE.backendBase}/api/soundscapes/settings`, { signal: AbortSignal.timeout(3000) });
      if (setRes.ok) {
        const cfg = await setRes.json();
        STATE.soundscapeEnabled = !!cfg.enabled;
        STATE.soundscapeTrack = cfg.current_track || STATE.soundscapeTrack || 'rain';
        STATE.soundscapeVolume = cfg.volume !== undefined ? cfg.volume : STATE.soundscapeVolume;
        STATE.soundscapeMuted = cfg.muted !== undefined ? !!cfg.muted : true;
        STATE.soundscapeCrossfade = cfg.crossfade_seconds || STATE.soundscapeCrossfade || 2.5;

        // Sync local storage
        localStorage.setItem('kuro_soundscape_enabled', STATE.soundscapeEnabled);
        localStorage.setItem('kuro_soundscape_track', STATE.soundscapeTrack);
        localStorage.setItem('kuro_soundscape_volume', STATE.soundscapeVolume);
        localStorage.setItem('kuro_soundscape_muted', STATE.soundscapeMuted);
        localStorage.setItem('kuro_soundscape_crossfade', STATE.soundscapeCrossfade);
      }
    } catch (err) {
      console.warn('[Kuro] Using cached soundscape preferences:', err);
    }

    applySoundscapePreferencesToUI();

    // If enabled and unmuted, start playback
    if (STATE.soundscapeEnabled && !STATE.soundscapeMuted) {
      playOrCrossfadeSoundscape(STATE.soundscapeTrack);
    }
  }

  function populateSoundscapeDropdown(catalog) {
    if (!DOM.settingSoundscapeTrack) return;
    const currentVal = DOM.settingSoundscapeTrack.value || STATE.soundscapeTrack;
    DOM.settingSoundscapeTrack.innerHTML = '';

    const icons = {
      rain: '🌧️',
      thunderstorm: '⛈️',
      japanese_forest: '🎋',
      night_city: '🌃',
      ocean_waves: '🌊',
      wind: '💨',
      fireplace: '🔥',
      space_ambience: '🌌'
    };

    catalog.forEach(item => {
      const opt = document.createElement('option');
      opt.value = item.id;
      const icon = icons[item.id] || '🎵';
      opt.textContent = `${icon} ${item.name}`;
      DOM.settingSoundscapeTrack.appendChild(opt);
    });

    if (currentVal) DOM.settingSoundscapeTrack.value = currentVal;
  }

  function applySoundscapePreferencesToUI() {
    if (DOM.settingSoundscapeEnabled) DOM.settingSoundscapeEnabled.checked = STATE.soundscapeEnabled;
    if (DOM.soundscapeSubcontrols) DOM.soundscapeSubcontrols.classList.toggle('disabled', !STATE.soundscapeEnabled);
    if (DOM.settingSoundscapeTrack) DOM.settingSoundscapeTrack.value = STATE.soundscapeTrack;
    if (DOM.settingSoundscapeVolume) DOM.settingSoundscapeVolume.value = STATE.soundscapeVolume;
    if (DOM.settingSoundscapeVolLabel) DOM.settingSoundscapeVolLabel.textContent = `${STATE.soundscapeVolume}%`;
    if (DOM.settingSoundscapeCrossfade) DOM.settingSoundscapeCrossfade.value = STATE.soundscapeCrossfade;
    if (DOM.settingSoundscapeFadeLabel) DOM.settingSoundscapeFadeLabel.textContent = `${STATE.soundscapeCrossfade}s`;

    updateSoundscapeHudIcon();
  }

  let soundscapeDebounceTimer = null;
  function saveSoundscapeSettingsToBackend() {
    clearTimeout(soundscapeDebounceTimer);
    soundscapeDebounceTimer = setTimeout(async () => {
      const payload = {
        enabled: STATE.soundscapeEnabled ? 1 : 0,
        current_track: STATE.soundscapeTrack,
        volume: STATE.soundscapeVolume,
        muted: STATE.soundscapeMuted ? 1 : 0,
        crossfade_seconds: STATE.soundscapeCrossfade
      };
      try {
        await backendPost('/api/soundscapes/settings', payload);
      } catch (e) {
        console.warn('[Kuro] Error saving soundscape settings:', e);
      }
    }, 400);
  }

  function updateSoundscapeSettingsFromUI() {
    if (DOM.settingSoundscapeEnabled) {
      STATE.soundscapeEnabled = DOM.settingSoundscapeEnabled.checked;
      localStorage.setItem('kuro_soundscape_enabled', STATE.soundscapeEnabled);
      if (DOM.soundscapeSubcontrols) {
        DOM.soundscapeSubcontrols.classList.toggle('disabled', !STATE.soundscapeEnabled);
      }
      if (!STATE.soundscapeEnabled) {
        stopSoundscapeAudio();
        showToast('Ambient Soundscape Disabled 🔇');
      } else {
        playOrCrossfadeSoundscape(STATE.soundscapeTrack);
        showToast(`Soundscape Enabled: ${getSoundscapeTrackName(STATE.soundscapeTrack)} 🎵`);
      }
    }

    if (DOM.settingSoundscapeTrack) {
      const newTrack = DOM.settingSoundscapeTrack.value;
      if (newTrack !== STATE.soundscapeTrack) {
        playOrCrossfadeSoundscape(newTrack);
        showToast(`Soundscape: ${getSoundscapeTrackName(newTrack)}`);
      }
    }

    if (DOM.settingSoundscapeVolume) {
      STATE.soundscapeVolume = parseInt(DOM.settingSoundscapeVolume.value, 10);
      localStorage.setItem('kuro_soundscape_volume', STATE.soundscapeVolume);
      if (DOM.settingSoundscapeVolLabel) DOM.settingSoundscapeVolLabel.textContent = `${STATE.soundscapeVolume}%`;
      const activeCh = STATE.activeAudioChannel === 'b' ? STATE.audioChannelB : STATE.audioChannelA;
      if (activeCh && !STATE.soundscapeMuted && STATE.soundscapeEnabled) {
        activeCh.volume = STATE.soundscapeVolume / 100.0;
      }
    }

    if (DOM.settingSoundscapeCrossfade) {
      STATE.soundscapeCrossfade = parseFloat(DOM.settingSoundscapeCrossfade.value);
      localStorage.setItem('kuro_soundscape_crossfade', STATE.soundscapeCrossfade);
      if (DOM.settingSoundscapeFadeLabel) DOM.settingSoundscapeFadeLabel.textContent = `${STATE.soundscapeCrossfade}s`;
    }

    updateSoundscapeHudIcon();
    saveSoundscapeSettingsToBackend();
  }

  // =========================================================================
  // INTERACTIVE ARTWORK INFORMATION PANEL (Key: I)
  // =========================================================================

  function openArtworkInfoModal() {
    if (!STATE.currentWallpaper) return;
    STATE.artworkInfoModalOpen = true;
    if (DOM.modalArtworkInfo) DOM.modalArtworkInfo.classList.remove('hidden');
    populateArtworkInfo(STATE.currentWallpaper);
  }

  function closeArtworkInfoModal() {
    STATE.artworkInfoModalOpen = false;
    if (DOM.modalArtworkInfo) DOM.modalArtworkInfo.classList.add('hidden');
  }

  function toggleArtworkInfoModal() {
    if (STATE.artworkInfoModalOpen) {
      closeArtworkInfoModal();
    } else {
      openArtworkInfoModal();
    }
  }

  async function populateArtworkInfo(wallpaper) {
    if (!wallpaper) return;

    if (DOM.artinfoTitle) DOM.artinfoTitle.textContent = wallpaper.anime || 'Popular Anime';
    if (DOM.artinfoCharacterSubtitle) {
      DOM.artinfoCharacterSubtitle.textContent = wallpaper.character ? `Character: ${wallpaper.character}` : '';
    }

    if (DOM.artinfoPreviewImg) {
      DOM.artinfoPreviewImg.src = wallpaper.url;
      DOM.artinfoPreviewImg.alt = `${wallpaper.anime || 'Anime'} artwork`;
    }

    const seq = STATE.currentSessionSequence || 1;
    if (DOM.artinfoSeqBadge) DOM.artinfoSeqBadge.textContent = `#${seq} in Session`;

    const q = wallpaper.quality_score != null ? Number(wallpaper.quality_score) : 75.0;
    const tech = wallpaper.technical_score != null ? Number(wallpaper.technical_score) : q;
    const pop = wallpaper.popularity_score != null ? Number(wallpaper.popularity_score) : q;

    if (DOM.artinfoQualityBadge) {
      DOM.artinfoQualityBadge.textContent = `★ ${q.toFixed(1)} Quality`;
    }

    // Specifications Grid
    if (DOM.artinfoValFranchise) DOM.artinfoValFranchise.textContent = wallpaper.anime || 'Popular Anime';

    if (DOM.artinfoValCharacter) {
      if (wallpaper.character && wallpaper.character.trim()) {
        DOM.artinfoValCharacter.textContent = wallpaper.character;
        DOM.artinfoValCharacter.classList.remove('unavailable');
      } else {
        DOM.artinfoValCharacter.innerHTML = '<span class="unavailable">Unavailable / Unverified</span>';
      }
    }

    if (DOM.artinfoValId) DOM.artinfoValId.textContent = wallpaper.id || 'Unavailable';
    if (DOM.artinfoValProvider) {
      DOM.artinfoValProvider.textContent = wallpaper.source || 'Wallhaven';
      DOM.artinfoValProvider.className = 'artinfo-spec-val provider-pill';
    }
    if (DOM.artinfoValStrategy) {
      const strat = wallpaper.query_strategy || (wallpaper.source === 'Wallhaven' ? 'verified_tag_id' : 'booru_failover');
      DOM.artinfoValStrategy.textContent = strat.replace(/_/g, ' ');
      DOM.artinfoValStrategy.className = `artinfo-spec-val strategy-pill ${strat}`;
    }
    if (DOM.artinfoValResolution) DOM.artinfoValResolution.textContent = wallpaper.resolution || 'High Res';

    // Calculate Aspect Ratio from image dimensions or metadata
    let ratioStr = wallpaper.aspect_ratio || null;
    let w = wallpaper.dimension_x;
    let h = wallpaper.dimension_y;
    if ((!w || !h) && wallpaper._preloadedImg && wallpaper._preloadedImg.naturalWidth > 0) {
      w = wallpaper._preloadedImg.naturalWidth;
      h = wallpaper._preloadedImg.naturalHeight;
    }
    if (!ratioStr && w && h && h > 0) {
      const val = (w / h).toFixed(2);
      let name = `${w}:${h}`;
      if (Math.abs(val - 1.78) <= 0.05) name = '16:9 Landscape';
      else if (Math.abs(val - 2.33) <= 0.08) name = '21:9 Ultrawide';
      else if (Math.abs(val - 0.56) <= 0.05) name = '9:16 Portrait';
      else if (Math.abs(val - 1.60) <= 0.05) name = '16:10';
      else if (Math.abs(val - 1.33) <= 0.05) name = '4:3';
      ratioStr = `${name} (${val}:1)`;
    }
    if (DOM.artinfoValRatio) {
      DOM.artinfoValRatio.textContent = ratioStr || '16:9 Standard';
    }

    // File Size formatting
    if (DOM.artinfoValFilesize) {
      if (wallpaper.file_size_formatted) {
        DOM.artinfoValFilesize.textContent = wallpaper.file_size_formatted;
        DOM.artinfoValFilesize.classList.remove('unavailable');
      } else if (wallpaper.file_size && Number(wallpaper.file_size) > 0) {
        const bytes = Number(wallpaper.file_size);
        const mb = (bytes / (1024 * 1024)).toFixed(2);
        DOM.artinfoValFilesize.textContent = `${mb} MB (${bytes.toLocaleString()} bytes)`;
        DOM.artinfoValFilesize.classList.remove('unavailable');
      } else {
        DOM.artinfoValFilesize.innerHTML = '<span class="unavailable">Unavailable</span>';
      }
    }

    // Community Favorites Count
    if (DOM.artinfoValFavorites) {
      if (wallpaper.favorites != null && wallpaper.favorites !== '') {
        DOM.artinfoValFavorites.textContent = `${Number(wallpaper.favorites).toLocaleString()} favorites`;
        DOM.artinfoValFavorites.classList.remove('unavailable');
      } else {
        DOM.artinfoValFavorites.innerHTML = '<span class="unavailable">Unavailable</span>';
      }
    }

    // Community Views Count
    if (DOM.artinfoValViews) {
      if (wallpaper.views != null && wallpaper.views !== '') {
        DOM.artinfoValViews.textContent = `${Number(wallpaper.views).toLocaleString()} views`;
        DOM.artinfoValViews.classList.remove('unavailable');
      } else {
        DOM.artinfoValViews.innerHTML = '<span class="unavailable">Unavailable</span>';
      }
    }

    // Upload Date
    if (DOM.artinfoValUploaddate) {
      if (wallpaper.upload_date && wallpaper.upload_date.trim()) {
        DOM.artinfoValUploaddate.textContent = wallpaper.upload_date;
        DOM.artinfoValUploaddate.classList.remove('unavailable');
      } else {
        DOM.artinfoValUploaddate.innerHTML = '<span class="unavailable">Unavailable</span>';
      }
    }

    // Uploader Information
    if (DOM.artinfoValUploader) {
      if (wallpaper.uploader && wallpaper.uploader.trim()) {
        DOM.artinfoValUploader.textContent = wallpaper.uploader;
        DOM.artinfoValUploader.classList.remove('unavailable');
      } else {
        DOM.artinfoValUploader.innerHTML = '<span class="unavailable">Unavailable</span>';
      }
    }

    // Original Source Link
    const srcLink = wallpaper.source_url || (wallpaper.source === 'Wallhaven' ? `https://wallhaven.cc/w/${wallpaper.id}` : null);
    if (DOM.artinfoValSource) {
      if (srcLink && (srcLink.startsWith('http://') || srcLink.startsWith('https://'))) {
        DOM.artinfoValSource.href = srcLink;
        DOM.artinfoValSource.textContent = srcLink;
        DOM.artinfoValSource.classList.remove('unavailable');
      } else if (srcLink) {
        DOM.artinfoValSource.removeAttribute('href');
        DOM.artinfoValSource.textContent = srcLink;
        DOM.artinfoValSource.classList.remove('unavailable');
      } else {
        DOM.artinfoValSource.removeAttribute('href');
        DOM.artinfoValSource.innerHTML = '<span class="unavailable">Unavailable</span>';
      }
    }

    // Display Sequence
    if (DOM.artinfoValSequence) {
      DOM.artinfoValSequence.textContent = `#${seq} in this session`;
    }

    // Technical Quality Score Breakdown
    if (DOM.artinfoValQuality) {
      DOM.artinfoValQuality.textContent = `${tech.toFixed(1)} / 100 (Overall: ${q.toFixed(1)})`;
      DOM.artinfoValQuality.title = `Technical Score: ${tech.toFixed(1)} | Popularity: ${pop.toFixed(1)}`;
    }

    // Safety & Moderation Status
    if (DOM.artinfoValSafety) {
      const sRating = (wallpaper.safety_rating || 'SAFE').toUpperCase();
      DOM.artinfoValSafety.textContent = `${sRating} (${wallpaper.safety_reason || 'Verified SFW'})`;
      DOM.artinfoValSafety.className = `artinfo-spec-val safety-badge ${sRating.toLowerCase()}`;
    }

    // Favorite button state
    const isFav = STATE.favorites.some(f => f.id === wallpaper.id);
    if (DOM.btnArtinfoFavorite) {
      DOM.btnArtinfoFavorite.classList.toggle('favorited', isFav);
      if (DOM.textArtinfoFav) DOM.textArtinfoFav.textContent = isFav ? 'Favorited' : 'Favorite';
    }

    // Fetch fresh database details in background to ensure zero stale fields
    try {
      const res = await fetch(`${STATE.backendBase}/api/wallpaper/${wallpaper.id}`, { signal: AbortSignal.timeout(2000) });
      if (res.ok) {
        const fresh = await res.json();
        // Update fields if fresh data has extra information
        if (fresh.uploader && DOM.artinfoValUploader) {
          DOM.artinfoValUploader.textContent = fresh.uploader;
          DOM.artinfoValUploader.classList.remove('unavailable');
        }
        if (fresh.upload_date && DOM.artinfoValUploaddate) {
          DOM.artinfoValUploaddate.textContent = fresh.upload_date;
          DOM.artinfoValUploaddate.classList.remove('unavailable');
        }
        if (fresh.file_size_formatted && DOM.artinfoValFilesize) {
          DOM.artinfoValFilesize.textContent = fresh.file_size_formatted;
          DOM.artinfoValFilesize.classList.remove('unavailable');
        }
        if (fresh.aspect_ratio && DOM.artinfoValRatio) {
          DOM.artinfoValRatio.textContent = fresh.aspect_ratio;
        }
        if (fresh.source_url && DOM.artinfoValSource) {
          DOM.artinfoValSource.href = fresh.source_url;
          DOM.artinfoValSource.textContent = fresh.source_url;
          DOM.artinfoValSource.classList.remove('unavailable');
        }
      }
    } catch (_) {}
  }

  function initArtworkInfoListeners() {
    if (DOM.btnQuickInfo) DOM.btnQuickInfo.addEventListener('click', toggleArtworkInfoModal);
    if (DOM.btnInfo) DOM.btnInfo.addEventListener('click', toggleArtworkInfoModal);
    if (DOM.btnArtinfoClose) DOM.btnArtinfoClose.addEventListener('click', closeArtworkInfoModal);

    // Clicking anywhere on meta-panel or quality badge opens the info panel
    if (DOM.tagQuality) {
      DOM.tagQuality.style.cursor = 'pointer';
      DOM.tagQuality.addEventListener('click', (e) => {
        e.stopPropagation();
        openArtworkInfoModal();
      });
    }

    // Backdrop click dismisses modal
    if (DOM.modalArtworkInfo) {
      DOM.modalArtworkInfo.addEventListener('click', (e) => {
        if (e.target === DOM.modalArtworkInfo) closeArtworkInfoModal();
      });
    }

    // Actions
    if (DOM.btnArtinfoOpenSource) {
      DOM.btnArtinfoOpenSource.addEventListener('click', () => {
        if (!STATE.currentWallpaper) return;
        const src = STATE.currentWallpaper.source_url ||
          (STATE.currentWallpaper.source === 'Wallhaven' ? `https://wallhaven.cc/w/${STATE.currentWallpaper.id}` : null);
        if (src && (src.startsWith('http://') || src.startsWith('https://'))) {
          window.open(src, '_blank');
        } else {
          showToast('Source link is unavailable for this artwork.');
        }
      });
    }

    if (DOM.btnArtinfoCopyUrl) {
      DOM.btnArtinfoCopyUrl.addEventListener('click', async () => {
        if (!STATE.currentWallpaper) return;
        const copyTarget = STATE.currentWallpaper.raw_url || STATE.currentWallpaper.url;
        try {
          await navigator.clipboard.writeText(copyTarget);
          if (DOM.textArtinfoCopy) DOM.textArtinfoCopy.textContent = '✓ Copied!';
          showToast('Artwork URL copied to clipboard 📋');
          setTimeout(() => {
            if (DOM.textArtinfoCopy) DOM.textArtinfoCopy.textContent = 'Copy URL';
          }, 2000);
        } catch (_) {
          showToast('Failed to copy to clipboard.');
        }
      });
    }

    if (DOM.btnArtinfoFavorite) {
      DOM.btnArtinfoFavorite.addEventListener('click', async () => {
        await toggleFavorite();
        const isFav = STATE.favorites.some(f => f.id === STATE.currentWallpaper.id);
        if (DOM.textArtinfoFav) DOM.textArtinfoFav.textContent = isFav ? 'Favorited' : 'Favorite';
      });
    }

    if (DOM.btnArtinfoViewOrig) {
      DOM.btnArtinfoViewOrig.addEventListener('click', () => {
        if (!STATE.currentWallpaper) return;
        const targetUrl = STATE.currentWallpaper.raw_url || STATE.currentWallpaper.url;
        window.open(targetUrl, '_blank');
      });
    }

    if (DOM.btnArtinfoHide) {
      DOM.btnArtinfoHide.addEventListener('click', () => {
        showToast('Artwork hidden, advancing to next slide ⏭️');
        STATE.wasExplicitlySkipped = true;
        displayNextWallpaper();
      });
    }

    if (DOM.btnArtinfoBlacklist) {
      DOM.btnArtinfoBlacklist.addEventListener('click', () => {
        blacklistCurrentWallpaper();
        closeArtworkInfoModal();
      });
    }

    if (DOM.btnArtinfoReport) {
      DOM.btnArtinfoReport.addEventListener('click', async () => {
        if (!STATE.currentWallpaper) return;
        const confirmed = confirm(
          `Report artwork "${STATE.currentWallpaper.id}" as unsafe/inappropriate?\n\nThis will permanently block it from appearing.`
        );
        if (!confirmed) return;
        try {
          const res = await fetch(`${STATE.backendBase}/api/moderation/report`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Kuro-Token': STATE.sessionToken },
            body: JSON.stringify({
              wallpaper_id: STATE.currentWallpaper.id,
              reason: 'User reported unsafe artwork from Artwork Info modal',
              block_character: false,
              block_artist: false
            })
          });
          if (res.ok) {
            showToast('Artwork permanently blocked and reported 🛡️');
            closeArtworkInfoModal();
            displayNextWallpaper();
          } else {
            showToast('Failed to submit artwork report.');
          }
        } catch (e) {
          showToast('Error communicating with moderation service.');
        }
      });
    }
  }

  // =========================================================================
  // WALLPAPER COMPOSITION & FOCAL POINT PROTECTION (Key: O)
  // =========================================================================

  async function loadCompositionSettings() {
    try {
      const res = await fetch(`${STATE.backendBase}/api/composition/settings`, { signal: AbortSignal.timeout(3000) });
      if (res.ok) {
        const settings = await res.json();
        STATE.compositionSettings = Object.assign(STATE.compositionSettings, settings);
      }
    } catch (_) {}
  }

  function openCompositionModal() {
    if (!STATE.currentWallpaper) return;
    STATE.compositionModalOpen = true;
    if (DOM.modalComposition) DOM.modalComposition.classList.remove('hidden');
    populateCompositionModal(STATE.currentWallpaper);
  }

  function closeCompositionModal() {
    STATE.compositionModalOpen = false;
    if (DOM.modalComposition) DOM.modalComposition.classList.add('hidden');
  }

  function toggleCompositionModal() {
    if (STATE.compositionModalOpen) {
      closeCompositionModal();
    } else {
      openCompositionModal();
    }
  }

  function populateCompositionModal(wallpaper) {
    if (!wallpaper) return;
    if (DOM.compCanvasImg) {
      DOM.compCanvasImg.src = wallpaper.url;
    }

    const comp = wallpaper.composition || {};
    STATE.editingFocalPoint = {
      x: comp.focal_x != null ? comp.focal_x : 50.0,
      y: comp.focal_y != null ? comp.focal_y : 35.0
    };
    STATE.editingDisplayMode = comp.display_mode || 'fill';
    STATE.editingBlurredBackdrop = comp.blurred_background !== false;
    STATE.editingCharacters = comp.characters ? JSON.parse(JSON.stringify(comp.characters)) : [];

    updateFocalReticleVisual();

    // Mode segmented buttons
    if (DOM.compModeBtns) {
      DOM.compModeBtns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === STATE.editingDisplayMode);
      });
    }

    // Blurred backdrop checkbox
    if (DOM.compCheckBlurredBackdrop) {
      DOM.compCheckBlurredBackdrop.checked = STATE.editingBlurredBackdrop;
    }

    renderCharacterPinsList();
  }

  function updateFocalReticleVisual() {
    const x = STATE.editingFocalPoint.x;
    const y = STATE.editingFocalPoint.y;
    if (DOM.compFocalReticle) {
      DOM.compFocalReticle.style.left = `${x}%`;
      DOM.compFocalReticle.style.top = `${y}%`;
    }
    if (DOM.reticleCoordBadge) {
      DOM.reticleCoordBadge.textContent = `${x.toFixed(1)}%, ${y.toFixed(1)}%`;
    }

    // Live update current active layer on wallpaper stage so user sees framing immediately
    const currentLayer = STATE.activeLayer === 'a' ? DOM.layerA : DOM.layerB;
    if (currentLayer) {
      currentLayer.style.setProperty('--focal-x', `${x}%`);
      currentLayer.style.setProperty('--focal-y', `${y}%`);
    }
  }

  function renderCharacterPinsList() {
    if (!DOM.compCharacterPinsList) return;
    DOM.compCharacterPinsList.innerHTML = '';
    if (!STATE.editingCharacters || STATE.editingCharacters.length === 0) {
      DOM.compCharacterPinsList.innerHTML = '<span style="font-size:0.75rem; color:#64748B;">No character targets pinned. Click "+ Add Character Pin" or drag the crosshairs.</span>';
      return;
    }

    STATE.editingCharacters.forEach((char, idx) => {
      const chip = document.createElement('button');
      chip.className = 'comp-character-chip';
      chip.textContent = `🎯 ${char.name || `Character ${idx + 1}`} (${char.x}%, ${char.y}%)`;
      chip.title = 'Click to focus on this character';
      chip.addEventListener('click', () => {
        STATE.editingFocalPoint = { x: char.x, y: char.y };
        updateFocalReticleVisual();
        showToast(`Framing focused on ${char.name || `Character ${idx + 1}`}`);
      });
      DOM.compCharacterPinsList.appendChild(chip);
    });
  }

  function initCompositionListeners() {
    if (DOM.btnCompositionToggle) DOM.btnCompositionToggle.addEventListener('click', toggleCompositionModal);
    if (DOM.btnCompClose) DOM.btnCompClose.addEventListener('click', closeCompositionModal);

    if (DOM.modalComposition) {
      DOM.modalComposition.addEventListener('click', (e) => {
        if (e.target === DOM.modalComposition) closeCompositionModal();
      });
    }

    // Interactive canvas click & drag
    if (DOM.compCanvasWrapper) {
      let isDragging = false;
      const setFocalFromEvent = (e) => {
        const rect = DOM.compCanvasWrapper.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return;
        const xPercent = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
        const yPercent = Math.max(0, Math.min(100, ((e.clientY - rect.top) / rect.height) * 100));
        STATE.editingFocalPoint = {
          x: Math.round(xPercent * 10) / 10,
          y: Math.round(yPercent * 10) / 10
        };
        updateFocalReticleVisual();
      };

      DOM.compCanvasWrapper.addEventListener('mousedown', (e) => {
        isDragging = true;
        setFocalFromEvent(e);
      });

      window.addEventListener('mousemove', (e) => {
        if (!isDragging || !STATE.compositionModalOpen) return;
        setFocalFromEvent(e);
      });

      window.addEventListener('mouseup', () => {
        isDragging = false;
      });

      // Touch support
      DOM.compCanvasWrapper.addEventListener('touchstart', (e) => {
        if (e.touches && e.touches[0]) {
          isDragging = true;
          setFocalFromEvent(e.touches[0]);
        }
      }, { passive: true });

      window.addEventListener('touchmove', (e) => {
        if (!isDragging || !STATE.compositionModalOpen) return;
        if (e.touches && e.touches[0]) setFocalFromEvent(e.touches[0]);
      }, { passive: true });

      window.addEventListener('touchend', () => {
        isDragging = false;
      });
    }

    // Aspect ratio preview buttons
    if (DOM.compAspectBtns) {
      DOM.compAspectBtns.forEach(btn => {
        btn.addEventListener('click', () => {
          DOM.compAspectBtns.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          const aspect = btn.dataset.aspect;
          if (DOM.compCanvasWrapper) {
            DOM.compCanvasWrapper.className = `comp-canvas-wrapper aspect-${aspect}`;
          }
        });
      });
    }

    // Display mode buttons (Fill, Fit, Original)
    if (DOM.compModeBtns) {
      DOM.compModeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
          DOM.compModeBtns.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          STATE.editingDisplayMode = btn.dataset.mode;
          // Live preview on active layer
          const currentLayer = STATE.activeLayer === 'a' ? DOM.layerA : DOM.layerB;
          if (currentLayer) {
            currentLayer.classList.remove('mode-fill', 'mode-fit', 'mode-original');
            currentLayer.classList.add(`mode-${STATE.editingDisplayMode}`);
          }
        });
      });
    }

    // Blurred backdrop toggle
    if (DOM.compCheckBlurredBackdrop) {
      DOM.compCheckBlurredBackdrop.addEventListener('change', (e) => {
        STATE.editingBlurredBackdrop = e.target.checked;
        const currentLayer = STATE.activeLayer === 'a' ? DOM.layerA : DOM.layerB;
        if (currentLayer) {
          currentLayer.classList.toggle('has-backdrop', STATE.editingBlurredBackdrop && (STATE.editingDisplayMode !== 'fill'));
        }
      });
    }

    // Presets
    if (DOM.compPresetBtns) {
      DOM.compPresetBtns.forEach(btn => {
        btn.addEventListener('click', () => {
          const x = parseFloat(btn.dataset.x);
          const y = parseFloat(btn.dataset.y);
          STATE.editingFocalPoint = { x, y };
          updateFocalReticleVisual();
        });
      });
    }

    // Add Character Pin
    if (DOM.btnCompAddChar) {
      DOM.btnCompAddChar.addEventListener('click', () => {
        const pinIdx = (STATE.editingCharacters.length || 0) + 1;
        const name = prompt(`Enter Character ${pinIdx} name (or leave default):`, `Character ${pinIdx}`) || `Character ${pinIdx}`;
        STATE.editingCharacters.push({
          id: pinIdx,
          name: name.trim(),
          x: STATE.editingFocalPoint.x,
          y: STATE.editingFocalPoint.y
        });
        renderCharacterPinsList();
        showToast(`Pinned ${name} at (${STATE.editingFocalPoint.x}%, ${STATE.editingFocalPoint.y}%)`);
      });
    }

    // Save button
    if (DOM.btnCompSave) {
      DOM.btnCompSave.addEventListener('click', async () => {
        if (!STATE.currentWallpaper) return;
        const payload = {
          focal_x: STATE.editingFocalPoint.x,
          focal_y: STATE.editingFocalPoint.y,
          display_mode: STATE.editingDisplayMode,
          blurred_background: STATE.editingBlurredBackdrop ? 1 : 0,
          characters: STATE.editingCharacters
        };

        try {
          const token = localStorage.getItem('kuro_token') || '';
          const res = await fetch(`${STATE.backendBase}/api/composition/${STATE.currentWallpaper.id}`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Kuro-Token': token
            },
            body: JSON.stringify(payload)
          });
          if (res.ok) {
            const data = await res.json();
            STATE.currentWallpaper.composition = data.composition;
            showToast('✓ Composition and focal coordinates saved! 🎯');
            closeCompositionModal();
          } else {
            showToast('Failed to save composition to backend.');
          }
        } catch (_) {
          showToast('Network error saving composition.');
        }
      });
    }

    // Reset button
    if (DOM.btnCompReset) {
      DOM.btnCompReset.addEventListener('click', async () => {
        if (!STATE.currentWallpaper) return;
        STATE.editingFocalPoint = { x: 50.0, y: 50.0 };
        STATE.editingDisplayMode = 'fill';
        STATE.editingBlurredBackdrop = true;
        STATE.editingCharacters = [];
        updateFocalReticleVisual();
        renderCharacterPinsList();

        try {
          const token = localStorage.getItem('kuro_token') || '';
          await fetch(`${STATE.backendBase}/api/composition/${STATE.currentWallpaper.id}`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Kuro-Token': token
            },
            body: JSON.stringify({ reset: true })
          });
          STATE.currentWallpaper.composition = null;
          showToast('Composition reset to defaults.');
        } catch (_) {}
      });
    }
  }

  // ==========================================================================
  // PERFORMANCE MONITORING & ADAPTIVE RENDERING CONTROLLER
  // ==========================================================================

  let fpsRaf = null;
  let fpsFrames = 0;
  let fpsLastSec = performance.now();
  let fpsRunning = false;

  function startFpsMeter() {
    if (fpsRunning) return;
    fpsRunning = true;
    fpsLastSec = performance.now();
    fpsFrames = 0;

    function loop(now) {
      if (!fpsRunning || document.hidden) {
        fpsRunning = false;
        return;
      }
      fpsFrames++;
      const elapsed = now - fpsLastSec;
      if (elapsed >= 1000) {
        const measured = Math.round((fpsFrames * 1000) / elapsed);
        STATE.currentFps = measured;
        STATE.fpsHistory.push(measured);
        if (STATE.fpsHistory.length > 20) STATE.fpsHistory.shift();

        evaluateAdaptiveQuality();

        if (STATE.diagnosticsOpen && DOM.perfValFps) {
          DOM.perfValFps.textContent = measured;
          updateFpsUi(measured);
        }

        fpsFrames = 0;
        fpsLastSec = now;
      }
      fpsRaf = requestAnimationFrame(loop);
    }

    fpsRaf = requestAnimationFrame(loop);
  }

  function stopFpsMeter() {
    fpsRunning = false;
    if (fpsRaf) {
      cancelAnimationFrame(fpsRaf);
      fpsRaf = null;
    }
  }

  function updateFpsUi(fps) {
    if (!DOM.perfFpsDot) return;
    if (fps >= 50) {
      DOM.perfFpsDot.className = 'perf-card-status-dot dot-green';
    } else if (fps >= 30) {
      DOM.perfFpsDot.className = 'perf-card-status-dot dot-yellow';
    } else {
      DOM.perfFpsDot.className = 'perf-card-status-dot dot-red';
    }
  }

  function getMemoryUsage() {
    if (typeof performance !== 'undefined' && performance.memory) {
      try {
        const used = performance.memory.usedJSHeapSize;
        const total = performance.memory.totalJSHeapSize;
        const limit = performance.memory.jsHeapSizeLimit;
        return {
          supported: true,
          usedMB: Math.round(used / (1024 * 1024)),
          totalMB: Math.round(total / (1024 * 1024)),
          limitMB: Math.round(limit / (1024 * 1024))
        };
      } catch (_) {}
    }
    return { supported: false, usedMB: null, totalMB: null, limitMB: null };
  }

  function evaluateAdaptiveQuality() {
    if (STATE.qualityProfile !== 'auto') return;
    if (STATE.fpsHistory.length < 5) return;

    const recent = STATE.fpsHistory.slice(-5);
    const avgRecent = recent.reduce((a, b) => a + b, 0) / recent.length;

    // Check memory pressure if available
    const mem = getMemoryUsage();
    const memoryPressure = mem.supported && mem.usedMB && mem.limitMB && (mem.usedMB / mem.limitMB > 0.85);

    if (avgRecent < 35 || memoryPressure) {
      if (STATE.effectiveQualityProfile === 'high') {
        setEffectiveQualityProfile('balanced', true);
      } else if (STATE.effectiveQualityProfile === 'balanced') {
        setEffectiveQualityProfile('low', true);
      }
    } else if (avgRecent >= 55 && !memoryPressure && STATE.fpsHistory.length >= 10) {
      const longRecent = STATE.fpsHistory.slice(-10);
      const longAvg = longRecent.reduce((a, b) => a + b, 0) / longRecent.length;
      if (longAvg >= 55) {
        if (STATE.effectiveQualityProfile === 'low') {
          setEffectiveQualityProfile('balanced', true);
        } else if (STATE.effectiveQualityProfile === 'balanced') {
          setEffectiveQualityProfile('high', true);
        }
      }
    }
  }

  function setEffectiveQualityProfile(effProfile, isAutoResolved = false) {
    STATE.effectiveQualityProfile = effProfile;
    document.body.dataset.qualityProfile = effProfile;

    if (DOM.perfProfilePill) {
      const modeLabel = STATE.qualityProfile === 'auto' ? `AUTO (${effProfile.toUpperCase()})` : effProfile.toUpperCase();
      DOM.perfProfilePill.textContent = modeLabel;
      DOM.perfProfilePill.className = `perf-status-badge profile-${effProfile}`;
    }

    if (typeof window.toggleParticleLoop === 'function') {
      window.toggleParticleLoop(effProfile !== 'low' && STATE.particlesEnabled && !isReducedMotionActive());
    }
  }

  async function selectQualityProfile(profile) {
    STATE.qualityProfile = profile;
    localStorage.setItem('kuro_quality_profile', profile);

    if (DOM.perfProfileButtons) {
      DOM.perfProfileButtons.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.profile === profile);
      });
    }

    if (profile === 'auto') {
      setEffectiveQualityProfile('high', true);
    } else {
      setEffectiveQualityProfile(profile, false);
    }

    try {
      await backendPost('/api/settings/quality-profile', { profile }, true);
    } catch (_) {}
  }

  function toggleDiagnosticsOverlay(forceState = null) {
    const shouldOpen = forceState !== null ? forceState : !STATE.diagnosticsOpen;
    STATE.diagnosticsOpen = shouldOpen;

    if (!DOM.perfDiagnosticsOverlay) return;

    if (shouldOpen) {
      DOM.perfDiagnosticsOverlay.classList.remove('hidden');
      updateDiagnosticsMetrics();
      if (!STATE.diagnosticsPollTimer) {
        STATE.diagnosticsPollTimer = setInterval(() => {
          if (!document.hidden && STATE.diagnosticsOpen) {
            updateDiagnosticsMetrics();
          }
        }, 2500);
      }
    } else {
      DOM.perfDiagnosticsOverlay.classList.add('hidden');
      if (STATE.diagnosticsPollTimer) {
        clearInterval(STATE.diagnosticsPollTimer);
        STATE.diagnosticsPollTimer = null;
      }
    }
  }

  async function updateDiagnosticsMetrics() {
    if (!STATE.diagnosticsOpen || document.hidden) return;

    // 1. Client Memory (feature detection)
    const mem = getMemoryUsage();
    if (DOM.perfValMem) {
      if (mem.supported) {
        DOM.perfValMem.textContent = mem.usedMB;
        if (DOM.perfUnitMem) DOM.perfUnitMem.textContent = 'MB';
        if (DOM.perfSubMem) DOM.perfSubMem.textContent = `Heap: ${mem.usedMB} / ${mem.limitMB} MB`;
        if (DOM.perfMemDot) {
          const usageRatio = mem.usedMB / (mem.limitMB || 1);
          DOM.perfMemDot.className = `perf-card-status-dot ${usageRatio > 0.8 ? 'dot-red' : usageRatio > 0.6 ? 'dot-yellow' : 'dot-green'}`;
        }
      } else {
        DOM.perfValMem.textContent = 'N/A';
        if (DOM.perfUnitMem) DOM.perfUnitMem.textContent = '';
        if (DOM.perfSubMem) DOM.perfSubMem.textContent = 'Non-Chromium';
        if (DOM.perfMemDot) DOM.perfMemDot.className = 'perf-card-status-dot dot-gray';
      }
    }

    // 2. Image Load/Decode Time
    if (DOM.perfValImgTime) {
      DOM.perfValImgTime.textContent = STATE.lastImageTotalMs || '--';
      if (DOM.perfSubImgTime) {
        DOM.perfSubImgTime.textContent = `Load: ${STATE.lastImageLoadMs || 0}ms · Dec: ${STATE.lastImageDecodeMs || 0}ms`;
      }
      if (DOM.perfImgDot) {
        const total = STATE.lastImageTotalMs || 0;
        DOM.perfImgDot.className = `perf-card-status-dot ${total > 1500 ? 'dot-red' : total > 600 ? 'dot-yellow' : 'dot-green'}`;
      }
    }

    // 3. Backend Metrics (/api/metrics)
    try {
      const data = await backendGet('/api/metrics');
      if (!data) return;

      // Prefetch Queue
      if (DOM.perfValQueue && data.prefetch_queue) {
        DOM.perfValQueue.textContent = data.prefetch_queue.unseen_count;
        if (DOM.perfSubQueue) {
          DOM.perfSubQueue.textContent = `Cached: ${data.prefetch_queue.cached_unseen_count} / Max: ${data.prefetch_queue.max_unseen_buffer}`;
        }
        if (DOM.perfQueueDot) {
          const qCount = data.prefetch_queue.unseen_count;
          DOM.perfQueueDot.className = `perf-card-status-dot ${qCount < 5 ? 'dot-red' : qCount < 15 ? 'dot-yellow' : 'dot-green'}`;
        }
      }

      // Cache Hit Rate
      if (DOM.perfValCacheRate && data.cache) {
        const hitRate = typeof data.cache.hit_rate_percent !== 'undefined' ? data.cache.hit_rate_percent : 100.0;
        DOM.perfValCacheRate.textContent = hitRate;
        if (DOM.perfSubCache) {
          DOM.perfSubCache.textContent = `Hits: ${data.cache.hits || 0} / ${data.cache.lookups || 0}`;
        }
        if (DOM.perfCacheDot) {
          DOM.perfCacheDot.className = `perf-card-status-dot ${hitRate < 60 ? 'dot-yellow' : 'dot-green'}`;
        }
      }

      // Backend Response Time
      if (DOM.perfValRespTime && data.backend_latency) {
        DOM.perfValRespTime.textContent = data.backend_latency.avg_latency_ms;
        if (DOM.perfSubResp) {
          DOM.perfSubResp.textContent = `Avg: ${data.backend_latency.avg_latency_ms}ms · P95: ${data.backend_latency.p95_latency_ms}ms`;
        }
        if (DOM.perfRespDot) {
          const avg = data.backend_latency.avg_latency_ms;
          DOM.perfRespDot.className = `perf-card-status-dot ${avg > 100 ? 'dot-red' : avg > 30 ? 'dot-yellow' : 'dot-green'}`;
        }
      }

      // SQLite Latency
      if (DOM.perfValSqlTime && data.sqlite_latency) {
        DOM.perfValSqlTime.textContent = data.sqlite_latency.avg_latency_ms;
        if (DOM.perfSubSql) {
          DOM.perfSubSql.textContent = `P95: ${data.sqlite_latency.p95_latency_ms}ms · Slow: ${data.sqlite_latency.slow_queries_count}`;
        }
        if (DOM.perfSqlDot) {
          const sqlAvg = data.sqlite_latency.avg_latency_ms;
          DOM.perfSqlDot.className = `perf-card-status-dot ${sqlAvg > 50 ? 'dot-red' : sqlAvg > 15 ? 'dot-yellow' : 'dot-green'}`;
        }
      }

      // API Failure Rate
      if (DOM.perfValFailRate && data.api_failures) {
        DOM.perfValFailRate.textContent = data.api_failures.failure_rate_percent;
        if (DOM.perfSubFail) {
          DOM.perfSubFail.textContent = `${data.api_failures.failed_requests} errs / ${data.api_failures.total_requests} reqs`;
        }
        if (DOM.perfApiDot) {
          const failRate = data.api_failures.failure_rate_percent;
          DOM.perfApiDot.className = `perf-card-status-dot ${failRate > 5 ? 'dot-red' : failRate > 0 ? 'dot-yellow' : 'dot-green'}`;
        }
      }

      // Active Workers
      if (DOM.perfValWorkers && data.workers) {
        DOM.perfValWorkers.textContent = data.workers.active_threads;
        if (DOM.perfSubWorkers) {
          DOM.perfSubWorkers.textContent = `Worker: ${data.workers.worker_state}`;
        }
        if (DOM.perfWorkerDot) {
          DOM.perfWorkerDot.className = `perf-card-status-dot ${data.workers.prefetch_worker_alive ? 'dot-green' : 'dot-yellow'}`;
        }
      }

      // Artwork Provider & Failover Status
      if (DOM.perfValProvider && data.providers) {
        const provData = data.providers;
        const activeName = provData.active_provider || 'Wallhaven';
        DOM.perfValProvider.textContent = activeName;
        if (DOM.perfSubProvider) {
          const failovers = provData.total_failovers || 0;
          DOM.perfSubProvider.textContent = `Failovers: ${failovers} · Active: ${activeName}`;
        }
        if (DOM.perfProviderDot) {
          const hasError = (provData.providers || []).some(p => p.health_status === 'rate_limited' || p.health_status === 'circuit_open');
          DOM.perfProviderDot.className = `perf-card-status-dot ${hasError ? 'dot-yellow' : 'dot-green'}`;
        }
      }
    } catch (err) {
      console.warn('Diagnostics metrics fetch failed', err);
    }
  }

  async function resetPerformanceMetrics() {
    try {
      await backendPost('/api/metrics/reset', {}, true);
      showToast('Performance Metrics Reset 🔄');
      updateDiagnosticsMetrics();
    } catch (_) {
      showToast('Failed to reset metrics ⚠️');
    }
  }

  // --- MULTI-PROVIDER ARTWORK FAILOVER CONTROLLER ---
  async function loadProviderSettings() {
    try {
      const resp = await fetch('/api/providers');
      if (!resp.ok) return;
      const data = await resp.json();
      renderProviderStatus(data);
    } catch (err) {
      console.warn('Failed to load provider settings', err);
    }
  }

  function renderProviderStatus(data) {
    if (!data) return;
    if (DOM.providerDiagActive) DOM.providerDiagActive.textContent = data.active_provider || 'Wallhaven';
    if (DOM.providerDiagFailovers) DOM.providerDiagFailovers.textContent = data.total_failovers || 0;

    const list = data.providers || [];
    list.forEach(p => {
      const key = (p.name || '').toLowerCase();
      let badgeEl = null;
      let toggleEl = null;

      if (key === 'wallhaven') {
        badgeEl = DOM.providerBadgeWallhaven;
        toggleEl = DOM.providerToggleWallhaven;
      } else if (key === 'safebooru') {
        badgeEl = DOM.providerBadgeSafebooru;
        toggleEl = DOM.providerToggleSafebooru;
      } else if (key === 'konachan') {
        badgeEl = DOM.providerBadgeKonachan;
        toggleEl = DOM.providerToggleKonachan;
      }

      if (toggleEl) {
        toggleEl.checked = Boolean(p.enabled);
      }

      if (badgeEl) {
        const status = p.health_status || 'healthy';
        badgeEl.className = `provider-status-badge ${status}`;
        if (status === 'rate_limited') {
          badgeEl.textContent = 'Rate Limited';
        } else if (status === 'circuit_open') {
          badgeEl.textContent = 'Circuit Open';
        } else if (status === 'degraded') {
          badgeEl.textContent = 'Degraded';
        } else if (status === 'disabled') {
          badgeEl.textContent = 'Disabled';
        } else if (status === 'probing') {
          badgeEl.textContent = 'Probing';
        } else {
          badgeEl.textContent = p.name === data.active_provider ? 'Active' : 'Standby';
        }
      }
    });
  }

  function initProviderSettings() {
    const attachToggle = (el, name) => {
      if (!el) return;
      el.addEventListener('change', async (e) => {
        try {
          const enabled = e.target.checked;
          await backendPost('/api/providers/toggle', { name, enabled }, true);
          showToast(`${name} ${enabled ? 'Enabled' : 'Disabled'} ✅`);
          loadProviderSettings();
        } catch (_) {
          showToast(`Failed to update ${name} ⚠️`);
          el.checked = !el.checked;
        }
      });
    };

    attachToggle(DOM.providerToggleWallhaven, 'Wallhaven');
    attachToggle(DOM.providerToggleSafebooru, 'Safebooru');
    attachToggle(DOM.providerToggleKonachan, 'Konachan');

    if (DOM.btnProviderResetCircuits) {
      DOM.btnProviderResetCircuits.addEventListener('click', async () => {
        try {
          await backendPost('/api/providers/reset-circuits', {}, true);
          showToast('All Circuit Breakers Reset to CLOSED ⚡');
          loadProviderSettings();
        } catch (_) {
          showToast('Failed to reset circuit breakers ⚠️');
        }
      });
    }

    loadProviderSettings();
  }

  // --- VERIFIED FRANCHISE TAG INTELLIGENCE CONTROLLER ---
  let CURRENT_CATALOG = {};

  async function loadTagCatalog() {
    if (!DOM.tagCatalogTbody) return;
    try {
      const res = await backendFetch('/api/franchises/catalog');
      CURRENT_CATALOG = res.catalog || {};
      if (DOM.tagCatalogCount) {
        DOM.tagCatalogCount.textContent = Object.keys(CURRENT_CATALOG).length;
      }
      renderTagCatalogTable(CURRENT_CATALOG);
    } catch (e) {
      console.warn('[TagIntelligence] Failed to load catalog:', e);
      if (DOM.tagCatalogTbody) {
        DOM.tagCatalogTbody.innerHTML = `<tr><td colspan="5" style="padding:10px; text-align:center; color:#f87171;">Failed to load catalog</td></tr>`;
      }
    }
  }

  function renderTagCatalogTable(catalog) {
    if (!DOM.tagCatalogTbody) return;
    const entries = Object.values(catalog);
    if (!entries.length) {
      DOM.tagCatalogTbody.innerHTML = `<tr><td colspan="5" style="padding:10px; text-align:center; color:#94a3b8;">No franchises found</td></tr>`;
      return;
    }

    DOM.tagCatalogTbody.innerHTML = entries.map(f => {
      const tagPills = (f.wallhaven_tag_ids || []).map(id => `<span class="tag-pill verified">id:${id}</span>`).join(' ') || '<span style="color:#64748b">none</span>';
      
      const charTagEntries = Object.entries(f.character_tag_ids || {});
      const charPills = charTagEntries.map(([cname, ids]) => `<span class="tag-pill alias" title="${cname}">${cname}: ${ids.join(',')}</span>`).join(' ') || '<span style="color:#64748b">--</span>';
      
      const exclKeywords = (f.excluded_keywords || []).map(k => `<span class="tag-pill exclusion">-${k}</span>`).join(' ');
      const exclTagIds = (f.excluded_tag_ids || []).map(id => `<span class="tag-pill exclusion">-id:${id}</span>`).join(' ');
      const exclPills = (exclKeywords || exclTagIds) ? `${exclTagIds} ${exclKeywords}` : '<span style="color:#64748b">none</span>';

      return `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.06);">
          <td style="padding: 6px 8px; font-weight: 600; color: #F1F5F9;">
            ${escapeHtml(f.name)}
            <div style="font-size: 0.68rem; color: #64748b; font-weight: normal;">${escapeHtml(f.slug)}</div>
          </td>
          <td style="padding: 6px 8px;">${tagPills}</td>
          <td style="padding: 6px 8px;">${charPills}</td>
          <td style="padding: 6px 8px;">${exclPills}</td>
          <td style="padding: 6px 8px; text-align: right;">
            <button class="secondary-btn btn-sm btn-edit-catalog-entry" data-slug="${escapeHtml(f.slug)}" style="padding: 2px 6px; font-size: 0.7rem;">Edit</button>
          </td>
        </tr>
      `;
    }).join('');

    // Attach edit handlers
    DOM.tagCatalogTbody.querySelectorAll('.btn-edit-catalog-entry').forEach(btn => {
      btn.addEventListener('click', () => {
        const slug = btn.dataset.slug;
        editCatalogEntry(slug);
      });
    });
  }

  async function editCatalogEntry(slug) {
    const f = CURRENT_CATALOG[slug];
    if (!f) return;
    const currentTags = (f.wallhaven_tag_ids || []).join(', ');
    const newTagsInput = prompt(`Edit Verified Wallhaven Tag IDs for "${f.name}" (comma-separated integers):`, currentTags);
    if (newTagsInput === null) return;

    const parsedTags = newTagsInput.split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n) && n > 0);
    const updated = Object.assign({}, f, { wallhaven_tag_ids: parsedTags });

    try {
      await backendPost('/api/franchises/catalog/update', { slug, entry: updated }, true);
      showToast(`Updated Tag IDs for ${f.name} ✅`);
      loadTagCatalog();
    } catch (e) {
      showToast(`Failed to update catalog entry ⚠️`);
    }
  }

  function initTagIntelligence() {
    if (DOM.btnVerifyTagId && DOM.inputVerifyTagId) {
      DOM.btnVerifyTagId.addEventListener('click', async () => {
        const val = DOM.inputVerifyTagId.value.trim();
        const tagId = parseInt(val, 10);
        if (!tagId || isNaN(tagId)) {
          showToast('Please enter a valid numeric tag ID');
          return;
        }

        if (DOM.tagVerifyResult) {
          DOM.tagVerifyResult.className = 'tag-verify-result';
          DOM.tagVerifyResult.classList.remove('hidden');
          DOM.tagVerifyResult.textContent = `Verifying tag ID ${tagId} online with Wallhaven API...`;
        }

        try {
          const res = await backendPost('/api/franchises/catalog/verify-tag', { tag_id: tagId }, true);
          const tag = res.tag || {};
          if (tag.is_valid) {
            DOM.tagVerifyResult.className = 'tag-verify-result success';
            DOM.tagVerifyResult.innerHTML = `<strong>Verified Tag:</strong> ${escapeHtml(tag.name)} &middot; Category: <em>${escapeHtml(tag.category || 'Unknown')}</em> &middot; Purity: ${escapeHtml(tag.purity || 'sfw')} &middot; ID: ${tag.id} (Cached locally in SQLite ✅)`;
          } else {
            DOM.tagVerifyResult.className = 'tag-verify-result error';
            DOM.tagVerifyResult.innerHTML = `<strong>Invalid or Unavailable:</strong> ${escapeHtml(tag.error || 'Tag not found on Wallhaven')}`;
          }
        } catch (e) {
          DOM.tagVerifyResult.className = 'tag-verify-result error';
          DOM.tagVerifyResult.textContent = `Verification error: ${e.message || e}`;
        }
      });
    }

    if (DOM.btnTagCatalogRefresh) {
      DOM.btnTagCatalogRefresh.addEventListener('click', () => {
        loadTagCatalog();
        showToast('Franchise catalog refreshed ↻');
      });
    }

    if (DOM.btnTagCatalogReset) {
      DOM.btnTagCatalogReset.addEventListener('click', async () => {
        if (!confirm('Are you sure you want to reset the franchise catalog to factory verified defaults? Any custom manual tag modifications will be restored.')) {
          return;
        }
        try {
          await backendPost('/api/franchises/catalog/reset', {}, true);
          showToast('Catalog reset to verified defaults ↺');
          loadTagCatalog();
        } catch (e) {
          showToast('Failed to reset catalog ⚠️');
        }
      });
    }

    loadTagCatalog();
  }

  function initPerformanceMonitoring() {
    startFpsMeter();
    selectQualityProfile(STATE.qualityProfile || 'auto');

    if (DOM.btnToggleDiagnostics) {
      DOM.btnToggleDiagnostics.addEventListener('click', () => toggleDiagnosticsOverlay());
    }
    if (DOM.btnPerfClose) {
      DOM.btnPerfClose.addEventListener('click', () => toggleDiagnosticsOverlay(false));
    }
    if (DOM.btnPerfResetMetrics) {
      DOM.btnPerfResetMetrics.addEventListener('click', resetPerformanceMetrics);
    }
    if (DOM.perfProfileButtons) {
      DOM.perfProfileButtons.forEach(btn => {
        btn.addEventListener('click', () => {
          selectQualityProfile(btn.dataset.profile);
        });
      });
    }
  }

  // --- VISUAL WALLPAPER HISTORY EXPLORER CONTROLLER ---
  function populateHistoryFranchiseDropdown(extraFranchises = []) {
    if (!DOM.histFilterFranchise) return;
    const currentVal = DOM.histFilterFranchise.value || 'all';
    const seen = new Set();
    const franchises = [];

    // From loaded state franchises
    if (Array.isArray(STATE.franchisesList)) {
      STATE.franchisesList.forEach(f => {
        const name = (typeof f === 'string' ? f : f.name || '').trim();
        if (name && !seen.has(name)) {
          seen.add(name);
          franchises.push(name);
        }
      });
    }

    // From extra franchises returned by history query
    if (Array.isArray(extraFranchises)) {
      extraFranchises.forEach(f => {
        const name = (typeof f === 'string' ? f : f.name || '').trim();
        if (name && !seen.has(name)) {
          seen.add(name);
          franchises.push(name);
        }
      });
    }

    franchises.sort((a, b) => a.localeCompare(b));

    let html = '<option value="all">All Franchises</option>';
    franchises.forEach(f => {
      html += `<option value="${escapeHtml(f)}">${escapeHtml(f)}</option>`;
    });

    DOM.histFilterFranchise.innerHTML = html;
    DOM.histFilterFranchise.value = seen.has(currentVal) ? currentVal : 'all';
  }

  function openHistoryExplorer() {
    if (!DOM.historyModal) return;
    DOM.historyModal.classList.remove('hidden');
    STATE.historyOpen = true;
    populateHistoryFranchiseDropdown();
    loadHistoryExplorer(STATE.historyPage || 1);
  }

  function closeHistoryExplorer() {
    if (!DOM.historyModal) return;
    DOM.historyModal.classList.add('hidden');
    STATE.historyOpen = false;
  }

  function toggleHistoryExplorer() {
    if (STATE.historyOpen || (DOM.historyModal && !DOM.historyModal.classList.contains('hidden'))) {
      closeHistoryExplorer();
    } else {
      closeArtworkInfoModal();
      closeCompositionModal();
      closeLibraryModal();
      closeControlCenter(true);
      openHistoryExplorer();
    }
  }

  function resetHistoryFilters() {
    if (DOM.histSearchInput) DOM.histSearchInput.value = '';
    if (DOM.histSearchClear) DOM.histSearchClear.classList.add('hidden');
    if (DOM.histFilterFranchise) DOM.histFilterFranchise.value = 'all';
    if (DOM.histFilterDate) DOM.histFilterDate.value = 'all';
    if (DOM.histFilterRes) DOM.histFilterRes.value = 'all';
    if (DOM.histSortBy) DOM.histSortBy.value = 'newest';
    STATE.historyFavsOnly = false;
    if (DOM.btnHistFavToggle) DOM.btnHistFavToggle.classList.remove('active');
    loadHistoryExplorer(1);
  }

  function exportHistory(format = 'json') {
    const safeFormat = format === 'csv' ? 'csv' : 'json';
    const exportUrl = `${STATE.backendBase}/api/history/export?format=${safeFormat}`;
    const dlLink = document.createElement('a');
    dlLink.href = exportUrl;
    dlLink.download = `kuro_wallpaper_history_${new Date().toISOString().slice(0, 10)}.${safeFormat}`;
    document.body.appendChild(dlLink);
    dlLink.click();
    document.body.removeChild(dlLink);
    showToast(`Downloading history metadata (${safeFormat.toUpperCase()})... 📥`);
  }

  async function loadHistoryExplorer(page = 1) {
    if (!DOM.historyGrid) return;
    STATE.historyPage = Math.max(1, parseInt(page, 10) || 1);

    const search = DOM.histSearchInput ? DOM.histSearchInput.value.trim() : '';
    const franchise = DOM.histFilterFranchise ? DOM.histFilterFranchise.value : 'all';
    const dateFilter = DOM.histFilterDate ? DOM.histFilterDate.value : 'all';
    const resolution = DOM.histFilterRes ? DOM.histFilterRes.value : 'all';
    const sortBy = DOM.histSortBy ? DOM.histSortBy.value : 'newest';
    const pageSize = parseInt(DOM.histPageSize ? DOM.histPageSize.value : '24', 10) || 24;
    const favsOnly = !!STATE.historyFavsOnly;

    // Build Active Filters summary
    const filterTokens = [];
    if (search) filterTokens.push(`Search: "${search}"`);
    if (franchise && franchise !== 'all') filterTokens.push(`Franchise: ${franchise}`);
    if (dateFilter && dateFilter !== 'all') filterTokens.push(`Date: ${dateFilter}`);
    if (resolution && resolution !== 'all') filterTokens.push(`Res: ${resolution}`);
    if (favsOnly) filterTokens.push('⭐ Favorites Only');
    if (sortBy && sortBy !== 'newest') filterTokens.push(`Sort: ${sortBy}`);

    if (DOM.histActiveFiltersLabel) {
      DOM.histActiveFiltersLabel.textContent = filterTokens.length > 0 ? `(${filterTokens.join(' • ')})` : '';
    }

    DOM.historyGrid.innerHTML = '<div style="color: #94a3b8; padding: 3rem; text-align: center; grid-column: 1 / -1; font-size: 0.88rem;">Loading wallpaper history...</div>';
    if (DOM.historyEmpty) DOM.historyEmpty.classList.add('hidden');

    const params = new URLSearchParams();
    params.append('page', STATE.historyPage);
    params.append('page_size', pageSize);
    if (search) params.append('q', search);
    if (franchise && franchise !== 'all') params.append('franchise', franchise);
    if (dateFilter && dateFilter !== 'all') params.append('date_filter', dateFilter);
    if (resolution && resolution !== 'all') params.append('resolution', resolution);
    if (favsOnly) params.append('favorites_only', 'true');
    if (sortBy) params.append('sort_by', sortBy);

    try {
      const res = await fetch(`${STATE.backendBase}/api/history?${params.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      const items = Array.isArray(data.items) ? data.items : [];
      const total = typeof data.total === 'number' ? data.total : items.length;
      STATE.historyTotalCount = total;
      STATE.historyTotalPages = Math.max(1, parseInt(data.total_pages, 10) || Math.ceil(total / pageSize) || 1);

      // Populate franchise filter options from backend discovery if available
      if (Array.isArray(data.franchises) && data.franchises.length > 0) {
        populateHistoryFranchiseDropdown(data.franchises);
      }

      // Update counters & badges
      if (DOM.histTotalBadge) {
        DOM.histTotalBadge.textContent = `${total} DISPLAYED`;
      }
      if (DOM.histResultsCount) {
        DOM.histResultsCount.textContent = `Showing ${items.length} of ${total} wallpapers`;
      }
      if (DOM.histCurrentPage) DOM.histCurrentPage.textContent = STATE.historyPage;
      if (DOM.histTotalPages) DOM.histTotalPages.textContent = STATE.historyTotalPages;

      // Update pagination button states
      if (DOM.btnHistFirst) DOM.btnHistFirst.disabled = (STATE.historyPage <= 1);
      if (DOM.btnHistPrev) DOM.btnHistPrev.disabled = (STATE.historyPage <= 1);
      if (DOM.btnHistNext) DOM.btnHistNext.disabled = (STATE.historyPage >= STATE.historyTotalPages);
      if (DOM.btnHistLast) DOM.btnHistLast.disabled = (STATE.historyPage >= STATE.historyTotalPages);

      // Render cards
      DOM.historyGrid.innerHTML = '';
      if (items.length === 0) {
        if (DOM.historyEmpty) DOM.historyEmpty.classList.remove('hidden');
      } else {
        if (DOM.historyEmpty) DOM.historyEmpty.classList.add('hidden');
        items.forEach(item => {
          const card = renderHistoryCard(item);
          DOM.historyGrid.appendChild(card);
        });
      }
    } catch (err) {
      console.warn('[Kuro] Error fetching wallpaper history:', err);
      DOM.historyGrid.innerHTML = `<div style="color: #f87171; padding: 2.5rem; text-align: center; grid-column: 1 / -1; font-size: 0.88rem;">Failed to load history: ${escapeHtml(err.message)}</div>`;
    }
  }

  function renderHistoryCard(item) {
    const card = document.createElement('div');
    card.className = 'hist-item-card';
    card.dataset.id = item.id;

    const thumbUrl = item.local_path ? `/${item.local_path}` : (item.thumbnail_url || (item.id ? `/api/image/${item.id}` : item.url));
    const fallbackUrl = item.url || '';
    const anime = escapeHtml(item.anime || 'Anime');
    const character = escapeHtml(item.character || 'Artwork');
    const res = escapeHtml(item.resolution || 'High Res');
    const simGroup = escapeHtml(item.similarity_group || 'Standard');
    const qualityScore = Math.round(item.quality_score || 0);

    // Format displayed timestamp
    let dateStr = 'Recently';
    if (item.displayed_at) {
      try {
        const d = new Date(item.displayed_at);
        if (!isNaN(d.getTime())) {
          dateStr = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' +
                    d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
        }
      } catch (_) {}
    }

    // Favorite status check
    const isFav = !!item.is_favorite || STATE.favorites.some(f => f.id === item.id);
    const favClass = isFav ? 'favorited' : '';
    const favIcon = isFav ? '❤️' : '🤍';

    // Quality pill styling
    const qualityColor = qualityScore >= 75 ? '#34d399' : qualityScore >= 50 ? '#38bdf8' : '#94a3b8';
    const qualityBg = qualityScore >= 75 ? 'rgba(16, 185, 129, 0.18)' : qualityScore >= 50 ? 'rgba(56, 189, 248, 0.18)' : 'rgba(148, 163, 184, 0.15)';

    // Wallhaven external link
    const sourceUrl = item.source_url || (item.id ? `https://wallhaven.cc/w/${item.id}` : '#');

    card.innerHTML = `
      <div class="hist-thumb-wrapper">
        <img class="hist-thumb-img"
             src="${thumbUrl}"
             loading="lazy"
             alt="${anime} - ${character}"
             onerror="if(this.src !== '${fallbackUrl}') { this.src = '${fallbackUrl}'; } else { this.style.display='none'; }">
        <div class="hist-badge-top-left" title="Resolution: ${res}">📐 ${res}</div>
        <div class="hist-badge-top-right">
          <span class="hist-quality-pill" style="color: ${qualityColor}; background: ${qualityBg};" title="Quality Score: ${qualityScore}/100">⭐ ${qualityScore}</span>
          <button class="hist-fav-toggle-btn ${favClass}" data-id="${item.id}" title="${isFav ? 'Remove from favorites' : 'Add to favorites'}">${favIcon}</button>
        </div>
      </div>
      <div class="hist-card-details">
        <div class="hist-anime-row">
          <span class="hist-anime-title" title="${anime}">${anime}</span>
          <span style="font-size: 0.65rem; color: #64748b; white-space: nowrap;" title="Displayed at: ${escapeHtml(item.displayed_at || '')}">🕒 ${dateStr}</span>
        </div>
        <div class="hist-character-name" title="${character}">${character}</div>
        <div class="hist-specs-row">
          <span style="font-family: var(--font-mono, monospace); color: #64748b;">#${escapeHtml(item.id)}</span>
          <span class="hist-similarity-badge" title="Similarity Group: ${simGroup}">🏷️ ${simGroup}</span>
        </div>
      </div>
      <div class="hist-card-actions-row">
        <button class="hist-btn-revisit" data-id="${item.id}" title="Revisit artwork on screen without duplicating history">
          ↺ Revisit
        </button>
        <a href="${sourceUrl}" target="_blank" rel="noopener noreferrer" class="hist-btn-source" title="Open original Wallhaven source">
          ↗ Source
        </a>
      </div>
    `;

    // Wire favorite button
    const favBtn = card.querySelector('.hist-fav-toggle-btn');
    if (favBtn) {
      favBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleHistoryFavorite(item, favBtn);
      });
    }

    // Wire revisit button
    const revisitBtn = card.querySelector('.hist-btn-revisit');
    if (revisitBtn) {
      revisitBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        revisitHistoricalArtwork(item.id);
      });
    }

    return card;
  }

  async function toggleHistoryFavorite(item, btnEl) {
    const isFav = STATE.favorites.some(f => f.id === item.id);
    if (isFav) {
      const idx = STATE.favorites.findIndex(f => f.id === item.id);
      if (idx >= 0) STATE.favorites.splice(idx, 1);
      if (btnEl) {
        btnEl.classList.remove('favorited');
        btnEl.textContent = '🤍';
        btnEl.title = 'Add to favorites';
      }
      showToast(`Removed #${item.id} from favorites`);
      backendPost('/api/favorite/remove', { id: item.id }).catch(() => {});
    } else {
      STATE.favorites.push(item);
      if (btnEl) {
        btnEl.classList.add('favorited');
        btnEl.textContent = '❤️';
        btnEl.title = 'Remove from favorites';
      }
      showToast(`Saved #${item.id} to favorites! ❤️`);
      backendPost('/api/favorite', {
        id: item.id,
        url: item.url,
        resolution: item.resolution || '',
        anime: item.anime || '',
        character: item.character || '',
        source: item.source || 'Wallhaven'
      }).catch(() => {});
    }
    localStorage.setItem('kuro_favorites', JSON.stringify(STATE.favorites));
    if (DOM.statFavoritesCount) DOM.statFavoritesCount.textContent = STATE.favorites.length;
    if (DOM.statLibFavorites) DOM.statLibFavorites.textContent = STATE.favorites.length;
    if (DOM.dashStatFavs) DOM.dashStatFavs.textContent = STATE.favorites.length;
  }

  async function revisitHistoricalArtwork(id) {
    try {
      showToast(`Loading artwork #${id} for revisit... ⏳`);
      const res = await backendPost('/api/history/revisit', { id });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.error || 'Failed to revisit wallpaper ⚠️');
        return;
      }
      const data = await res.json();
      const wp = data.wallpaper;
      if (!wp) {
        showToast('Wallpaper not found in history ⚠️');
        return;
      }

      closeHistoryExplorer();
      await displaySpecificWallpaper(wp);
      showToast(`Revisiting: ${wp.anime || 'Anime Art'} ↺`);
    } catch (err) {
      console.error('Revisit failed:', err);
      showToast('Failed to revisit wallpaper ⚠️');
    }
  }

  function initHistoryExplorer() {
    if (DOM.btnHistoryOpen) {
      DOM.btnHistoryOpen.addEventListener('click', () => toggleHistoryExplorer());
    }
    if (DOM.btnHistoryClose) {
      DOM.btnHistoryClose.addEventListener('click', () => closeHistoryExplorer());
    }
    if (DOM.libTabHistoryBtn) {
      DOM.libTabHistoryBtn.addEventListener('click', () => {
        closeLibraryModal();
        openHistoryExplorer();
      });
    }

    // Debounced search input
    if (DOM.histSearchInput) {
      const handleSearch = debounce(() => {
        const val = DOM.histSearchInput.value.trim();
        if (DOM.histSearchClear) {
          DOM.histSearchClear.classList.toggle('hidden', val.length === 0);
        }
        loadHistoryExplorer(1);
      }, 300);

      DOM.histSearchInput.addEventListener('input', handleSearch);
      DOM.histSearchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          loadHistoryExplorer(1);
        }
      });
    }

    if (DOM.histSearchClear) {
      DOM.histSearchClear.addEventListener('click', () => {
        if (DOM.histSearchInput) DOM.histSearchInput.value = '';
        DOM.histSearchClear.classList.add('hidden');
        loadHistoryExplorer(1);
      });
    }

    // Favorites only filter pill toggle
    if (DOM.btnHistFavToggle) {
      DOM.btnHistFavToggle.addEventListener('click', () => {
        STATE.historyFavsOnly = !STATE.historyFavsOnly;
        DOM.btnHistFavToggle.classList.toggle('active', STATE.historyFavsOnly);
        loadHistoryExplorer(1);
      });
    }

    // Filter selectors
    if (DOM.histFilterFranchise) {
      DOM.histFilterFranchise.addEventListener('change', () => loadHistoryExplorer(1));
    }
    if (DOM.histFilterDate) {
      DOM.histFilterDate.addEventListener('change', () => loadHistoryExplorer(1));
    }
    if (DOM.histFilterRes) {
      DOM.histFilterRes.addEventListener('change', () => loadHistoryExplorer(1));
    }
    if (DOM.histSortBy) {
      DOM.histSortBy.addEventListener('change', () => loadHistoryExplorer(1));
    }
    if (DOM.btnHistRefresh) {
      DOM.btnHistRefresh.addEventListener('click', () => loadHistoryExplorer(STATE.historyPage));
    }
    if (DOM.btnHistResetFilters) {
      DOM.btnHistResetFilters.addEventListener('click', resetHistoryFilters);
    }

    // Metadata Export buttons
    if (DOM.btnHistExportJson) {
      DOM.btnHistExportJson.addEventListener('click', () => exportHistory('json'));
    }
    if (DOM.btnHistExportCsv) {
      DOM.btnHistExportCsv.addEventListener('click', () => exportHistory('csv'));
    }

    // Pagination buttons
    if (DOM.btnHistFirst) {
      DOM.btnHistFirst.addEventListener('click', () => {
        if (STATE.historyPage > 1) loadHistoryExplorer(1);
      });
    }
    if (DOM.btnHistPrev) {
      DOM.btnHistPrev.addEventListener('click', () => {
        if (STATE.historyPage > 1) loadHistoryExplorer(STATE.historyPage - 1);
      });
    }
    if (DOM.btnHistNext) {
      DOM.btnHistNext.addEventListener('click', () => {
        if (STATE.historyPage < STATE.historyTotalPages) loadHistoryExplorer(STATE.historyPage + 1);
      });
    }
    if (DOM.btnHistLast) {
      DOM.btnHistLast.addEventListener('click', () => {
        if (STATE.historyPage < STATE.historyTotalPages) loadHistoryExplorer(STATE.historyTotalPages);
      });
    }
    if (DOM.histPageSize) {
      DOM.histPageSize.addEventListener('change', () => {
        loadHistoryExplorer(1);
      });
    }
  }

  // =========================================================================
  // CONTENT SAFETY & MODERATION SYSTEM
  // =========================================================================

  let activeBlockFilter = 'all';

  async function fetchModerationSettings() {
    try {
      const res = await fetch(`${STATE.backendBase}/api/moderation/settings`);
      if (res.ok) {
        const data = await res.json();
        const cfg = data.settings || {};
        if (DOM.settingModStrictMode) DOM.settingModStrictMode.checked = Boolean(cfg.strict_mode);
        if (DOM.settingModAllowReview) DOM.settingModAllowReview.checked = Boolean(cfg.allow_review_queue);
        if (DOM.settingModAutoblockReported) DOM.settingModAutoblockReported.checked = Boolean(cfg.auto_block_reported);
        if (DOM.settingModMinTags) DOM.settingModMinTags.value = cfg.min_tags_required || 1;
      }
    } catch (_) {}
  }

  async function saveModerationPolicy() {
    const payload = {
      strict_mode: DOM.settingModStrictMode ? DOM.settingModStrictMode.checked : true,
      allow_review_queue: DOM.settingModAllowReview ? DOM.settingModAllowReview.checked : true,
      auto_block_reported: DOM.settingModAutoblockReported ? DOM.settingModAutoblockReported.checked : true,
      min_tags_required: DOM.settingModMinTags ? parseInt(DOM.settingModMinTags.value, 10) || 1 : 1
    };
    try {
      const res = await fetch(`${STATE.backendBase}/api/moderation/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Kuro-Token': STATE.sessionToken },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        showToast('Safety & moderation policy saved 🛡️');
      } else {
        showToast('Failed to save moderation policy.');
      }
    } catch (e) {
      showToast('Error communicating with moderation API.');
    }
  }

  async function fetchBlockedEntities(filterType) {
    const type = filterType !== undefined ? filterType : activeBlockFilter;
    const url = type && type !== 'all'
      ? `${STATE.backendBase}/api/moderation/blocked?entity_type=${encodeURIComponent(type)}`
      : `${STATE.backendBase}/api/moderation/blocked`;
    try {
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();
      const list = data.blocked_entities || [];
      renderBlockedEntities(list);
    } catch (_) {}
  }

  function renderBlockedEntities(list) {
    if (!DOM.blockedEntitiesList) return;
    if (!list || list.length === 0) {
      DOM.blockedEntitiesList.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 0.8rem;">No blocked entities found for this filter.</div>';
      return;
    }
    DOM.blockedEntitiesList.innerHTML = list.map(item => `
      <div class="blocked-item-row" data-id="${item.id}">
        <div class="blocked-item-left">
          <span class="blocked-type-badge">${escapeHtml(item.entity_type)}</span>
          <span class="blocked-item-value">${escapeHtml(item.entity_value)}</span>
          ${item.reason ? `<span class="blocked-item-reason">(${escapeHtml(item.reason)})</span>` : ''}
        </div>
        <button class="btn-unblock" data-id="${item.id}" data-type="${escapeHtml(item.entity_type)}" data-value="${escapeHtml(item.entity_value)}" title="Unblock this item">Unblock</button>
      </div>
    `).join('');

    DOM.blockedEntitiesList.querySelectorAll('.btn-unblock').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const id = parseInt(e.target.dataset.id, 10);
        const type = e.target.dataset.type;
        const val = e.target.dataset.value;
        await unblockEntity(id, type, val);
      });
    });
  }

  async function addBlockedEntity() {
    if (!DOM.inputBlockType || !DOM.inputBlockValue) return;
    const type = DOM.inputBlockType.value;
    const value = DOM.inputBlockValue.value.trim();
    const reason = DOM.inputBlockReason ? DOM.inputBlockReason.value.trim() : '';
    if (!value) {
      showToast('Please enter an entity value to block.');
      return;
    }
    try {
      const res = await fetch(`${STATE.backendBase}/api/moderation/block`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Kuro-Token': STATE.sessionToken },
        body: JSON.stringify({ entity_type: type, entity_value: value, reason: reason })
      });
      if (res.ok) {
        showToast(`Blocked ${type}: "${value}" 🚫`);
        DOM.inputBlockValue.value = '';
        if (DOM.inputBlockReason) DOM.inputBlockReason.value = '';
        fetchBlockedEntities();
      } else {
        showToast('Failed to add block.');
      }
    } catch (_) {
      showToast('Error communicating with moderation API.');
    }
  }

  async function unblockEntity(id, type, val) {
    try {
      const res = await fetch(`${STATE.backendBase}/api/moderation/unblock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Kuro-Token': STATE.sessionToken },
        body: JSON.stringify({ entity_id: id, entity_type: type, entity_value: val })
      });
      if (res.ok) {
        showToast(`Unblocked ${type}: "${val}"`);
        fetchBlockedEntities();
      } else {
        showToast('Failed to unblock item.');
      }
    } catch (_) {
      showToast('Error communicating with moderation API.');
    }
  }

  async function fetchReviewQueue() {
    try {
      const res = await fetch(`${STATE.backendBase}/api/moderation/review-queue?limit=50&decision=PENDING`);
      if (!res.ok) return;
      const data = await res.json();
      const items = data.queue || [];
      renderReviewQueue(items);
    } catch (_) {}
  }

  function renderReviewQueue(items) {
    if (!DOM.reviewQueueList) return;
    if (!items || items.length === 0) {
      DOM.reviewQueueList.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 0.8rem;">No ambiguous artworks in review queue. Clean! ✨</div>';
      return;
    }
    DOM.reviewQueueList.innerHTML = items.map(q => {
      const wp = q.wallpaper || {};
      const thumb = wp.thumbnail_url || wp.url || '';
      return `
        <div class="review-queue-card" data-id="${escapeHtml(q.id)}">
          <img class="review-queue-thumb" src="${escapeHtml(thumb)}" alt="${escapeHtml(wp.anime || 'Artwork')}" onerror="this.style.display='none'" />
          <div class="review-queue-info">
            <div class="review-queue-header">
              <span class="review-queue-id">${escapeHtml(q.id)}</span>
              <span class="safety-badge ambiguous">${escapeHtml(q.safety_rating)}</span>
              <span style="color: var(--text-dim); font-size: 0.7rem;">${escapeHtml(wp.source || 'Provider')}</span>
            </div>
            <div class="review-queue-reason">${escapeHtml(q.failure_reason)}</div>
          </div>
          <div class="review-queue-actions">
            <button class="btn-queue-approve" data-id="${escapeHtml(q.id)}">✓ Approve SFW</button>
            <button class="btn-queue-reject" data-id="${escapeHtml(q.id)}">✕ Reject Unsafe</button>
          </div>
        </div>
      `;
    }).join('');

    DOM.reviewQueueList.querySelectorAll('.btn-queue-approve').forEach(btn => {
      btn.addEventListener('click', () => actionReviewQueueItem(btn.dataset.id, 'APPROVE'));
    });
    DOM.reviewQueueList.querySelectorAll('.btn-queue-reject').forEach(btn => {
      btn.addEventListener('click', () => actionReviewQueueItem(btn.dataset.id, 'REJECT'));
    });
  }

  async function actionReviewQueueItem(wallpaperId, decision) {
    try {
      const res = await fetch(`${STATE.backendBase}/api/moderation/review-action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Kuro-Token': STATE.sessionToken },
        body: JSON.stringify({ wallpaper_id: wallpaperId, decision: decision })
      });
      if (res.ok) {
        showToast(decision === 'APPROVE' ? 'Artwork approved for display! ✓' : 'Artwork rejected and blocked ✕');
        fetchReviewQueue();
      } else {
        showToast('Failed to apply review decision.');
      }
    } catch (_) {
      showToast('Error communicating with review API.');
    }
  }

  function initModerationSystem() {
    if (DOM.btnSaveModPolicy) {
      DOM.btnSaveModPolicy.addEventListener('click', saveModerationPolicy);
    }
    if (DOM.btnAddBlock) {
      DOM.btnAddBlock.addEventListener('click', addBlockedEntity);
    }
    if (DOM.blockFilterPills) {
      DOM.blockFilterPills.forEach(pill => {
        pill.addEventListener('click', () => {
          DOM.blockFilterPills.forEach(p => p.classList.remove('active'));
          pill.classList.add('active');
          activeBlockFilter = pill.dataset.bfilter || 'all';
          fetchBlockedEntities(activeBlockFilter);
        });
      });
    }
  }

  // Boot
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
