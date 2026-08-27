@echo off
chcp 65001 >nul
setlocal

set PYTHON=E:\software\anaconda\envs\poirot\python.exe
set LOG=E:\python_file\agent_practice\poirot\bench\data\runs\bench_run.log

echo ============================================
echo  Bench Suite Runner - Started %date% %time%
echo ============================================
echo ============================================ > "%LOG%" 2>&1
echo  Bench Suite Runner - Started %date% %time% >> "%LOG%" 2>&1
echo ============================================ >> "%LOG%" 2>&1

:: ---- Suite B ----
echo [B] Starting run_gov_experiment ... %time%
echo [B] Starting run_gov_experiment ... %time% >> "%LOG%" 2>&1
"%PYTHON%" -m bench.b_governance.run_gov_experiment >> "%LOG%" 2>&1
echo [B] run_gov_experiment finished (code %errorlevel%) %time%
echo [B] run_gov_experiment finished (code %errorlevel%) %time% >> "%LOG%" 2>&1

echo [B] Starting analyze_gov ... %time%
echo [B] Starting analyze_gov ... %time% >> "%LOG%" 2>&1
"%PYTHON%" -m bench.b_governance.analyze_gov >> "%LOG%" 2>&1
echo [B] analyze_gov finished (code %errorlevel%) %time%
echo [B] analyze_gov finished (code %errorlevel%) %time% >> "%LOG%" 2>&1

:: ---- Suite C ----
echo [C] Starting baseline ... %time%
echo [C] Starting baseline ... %time% >> "%LOG%" 2>&1
"%PYTHON%" -m bench.c_skill.run_skill_bench --phase baseline >> "%LOG%" 2>&1
echo [C] baseline finished (code %errorlevel%) %time%
echo [C] baseline finished (code %errorlevel%) %time% >> "%LOG%" 2>&1

echo [C] Starting run_evolution ... %time%
echo [C] Starting run_evolution ... %time% >> "%LOG%" 2>&1
"%PYTHON%" -m bench.c_skill.run_evolution >> "%LOG%" 2>&1
echo [C] run_evolution finished (code %errorlevel%) %time%
echo [C] run_evolution finished (code %errorlevel%) %time% >> "%LOG%" 2>&1

echo [C] Starting post ... %time%
echo [C] Starting post ... %time% >> "%LOG%" 2>&1
"%PYTHON%" -m bench.c_skill.run_skill_bench --phase post >> "%LOG%" 2>&1
echo [C] post finished (code %errorlevel%) %time%
echo [C] post finished (code %errorlevel%) %time% >> "%LOG%" 2>&1

echo [C] Starting analyze_skill ... %time%
echo [C] Starting analyze_skill ... %time% >> "%LOG%" 2>&1
"%PYTHON%" -m bench.c_skill.analyze_skill >> "%LOG%" 2>&1
echo [C] analyze_skill finished (code %errorlevel%) %time%
echo [C] analyze_skill finished (code %errorlevel%) %time% >> "%LOG%" 2>&1

:: ---- Suite D ----
echo [D] Starting run_multiagent_bench --timeout 900 ... %time%
echo [D] Starting run_multiagent_bench --timeout 900 ... %time% >> "%LOG%" 2>&1
"%PYTHON%" -m bench.d_multiagent.run_multiagent_bench --timeout 900 >> "%LOG%" 2>&1
echo [D] run_multiagent_bench finished (code %errorlevel%) %time%
echo [D] run_multiagent_bench finished (code %errorlevel%) %time% >> "%LOG%" 2>&1

echo [D] Starting analyze_multiagent ... %time%
echo [D] Starting analyze_multiagent ... %time% >> "%LOG%" 2>&1
"%PYTHON%" -m bench.d_multiagent.analyze_multiagent >> "%LOG%" 2>&1
echo [D] analyze_multiagent finished (code %errorlevel%) %time%
echo [D] analyze_multiagent finished (code %errorlevel%) %time% >> "%LOG%" 2>&1

:: ---- Suite A ----
echo [A] Starting run_gaia ... %time%
echo [A] Starting run_gaia ... %time% >> "%LOG%" 2>&1
"%PYTHON%" -m bench.a_gaia.run_gaia >> "%LOG%" 2>&1
echo [A] run_gaia finished (code %errorlevel%) %time%
echo [A] run_gaia finished (code %errorlevel%) %time% >> "%LOG%" 2>&1

echo [A] Starting judge ... %time%
echo [A] Starting judge ... %time% >> "%LOG%" 2>&1
"%PYTHON%" -m bench.a_gaia.judge >> "%LOG%" 2>&1
echo [A] judge finished (code %errorlevel%) %time%
echo [A] judge finished (code %errorlevel%) %time% >> "%LOG%" 2>&1

echo [A] Starting score_gaia ... %time%
echo [A] Starting score_gaia ... %time% >> "%LOG%" 2>&1
"%PYTHON%" -m bench.a_gaia.score_gaia >> "%LOG%" 2>&1
echo [A] score_gaia finished (code %errorlevel%) %time%
echo [A] score_gaia finished (code %errorlevel%) %time% >> "%LOG%" 2>&1

echo ============================================
echo  ALL SUITES DONE - %date% %time%
echo ============================================
echo  ALL SUITES DONE - %date% %time% >> "%LOG%" 2>&1
echo.
echo Log saved to: %LOG%
echo Press any key to close...
pause >nul

endlocal
