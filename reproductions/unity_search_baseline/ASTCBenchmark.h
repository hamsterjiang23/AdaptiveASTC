#pragma once

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <string>

// This observer is enabled only by ASTC_BENCHMARK_LOG. It never selects a candidate.
namespace ASTCBenchmark
{
    typedef std::chrono::steady_clock Clock;

    struct Record
    {
        std::string asset;
        std::string block;
        std::string preset;
        std::string reason;
        Clock::time_point started;
        Clock::time_point searchStarted;
        double searchMs = 0;
        double formatMs = 0;
        int candidates = 0;
        int measured = 0;
        int reusedPayloads = 0;
        bool cacheHit = false;
        bool searchExecuted = false;
        bool success = false;
    };

    inline Record*& Active()
    {
        static thread_local Record* record = NULL;
        return record;
    }

    inline double Elapsed(Clock::time_point start)
    {
        return std::chrono::duration<double, std::milli>(Clock::now() - start).count();
    }

    inline std::string Escape(const std::string& value)
    {
        std::ostringstream out;
        for (unsigned char c : value)
        {
            if (c == '"' || c == '\\') out << '\\' << c;
            else if (c < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << (int)c << std::dec;
            else out << c;
        }
        return out.str();
    }

    class PipelineScope
    {
        Record record;
        Record* previous;
        const char* path;
    public:
        explicit PipelineScope(const char* asset) : previous(Active()), path(std::getenv("ASTC_BENCHMARK_LOG"))
        {
            if (path == NULL || path[0] == 0 || asset == NULL || previous != NULL) return;
            record.asset = asset;
            record.started = Clock::now();
            Active() = &record;
        }

        ~PipelineScope()
        {
            if (Active() != &record) return;
            const double pipelineMs = Elapsed(record.started);
            Active() = previous;
            std::ostringstream out;
            out << std::setprecision(12)
                << "{\"asset\":\"" << Escape(record.asset)
                << "\",\"block_size\":\"" << Escape(record.block)
                << "\",\"preset\":\"" << Escape(record.preset)
                << "\",\"selection_reason\":\"" << Escape(record.reason)
                << "\",\"search_ms\":" << record.searchMs
                << ",\"format_ms\":" << record.formatMs
                << ",\"select_and_encode_ms\":" << pipelineMs
                << ",\"candidates_attempted\":" << record.candidates
                << ",\"candidates_measured\":" << record.measured
                << ",\"payload_reuses\":" << record.reusedPayloads
                << ",\"cache_hit\":" << (record.cacheHit ? "true" : "false")
                << ",\"search_executed\":" << (record.searchExecuted ? "true" : "false")
                << ",\"success\":" << (record.success ? "true" : "false") << "}\n";
            static std::mutex fileMutex;
            std::lock_guard<std::mutex> guard(fileMutex);
            FILE* file = std::fopen(path, "ab");
            if (file != NULL)
            {
                const std::string line = out.str();
                std::fwrite(line.data(), 1, line.size(), file);
                std::fclose(file);
            }
        }
    };

    class FormatScope
    {
        Clock::time_point started;
    public:
        FormatScope() : started(Clock::now()) {}
        ~FormatScope() { if (Active()) Active()->formatMs += Elapsed(started); }
    };

    inline void SearchStart()
    {
        if (Active()) { Active()->searchExecuted = true; Active()->searchStarted = Clock::now(); }
    }
    inline void SearchEnd() { if (Active()) Active()->searchMs += Elapsed(Active()->searchStarted); }
    inline void CacheHit() { if (Active()) { Active()->cacheHit = true; Active()->reason = "parameter_cache"; } }
    inline void Reason(const char* reason) { if (Active()) Active()->reason = reason; }
    inline void Candidate() { if (Active()) ++Active()->candidates; }
    inline void Measured() { if (Active()) ++Active()->measured; }
    inline void Reused() { if (Active()) ++Active()->reusedPayloads; }
    inline void Selected(const char* block, const char* preset)
    {
        if (Active()) { Active()->block = block; Active()->preset = preset; Active()->success = true; }
    }
}
